const assert = require('node:assert/strict');
const {chromium} = require(process.env.QUEEZO_PLAYWRIGHT || 'playwright');

// Run only against the disposable site described in docs/STUDY_ROOMS.md.
const baseURL = process.env.QUEEZO_ROOM_TEST_URL || 'http://127.0.0.1:18711';
const password = 'A disposable room test passphrase';
const signupOrigin = process.env.QUEEZO_ROOM_TEST_SIGNUP_URL || baseURL;
async function call(context, method, path, data, csrf, expected) {
  const response = await context.request.fetch((path === '/auth/signup' ? signupOrigin : baseURL) + '/api' + path,{
    method,data,headers:{origin:baseURL,...(csrf ? {'x-csrf-token':csrf} : {})}
  });
  assert.equal(response.status(),expected,path + ' ' + await response.text());
  return expected === 204 ? null : response.json();
}
(async () => {
  const browser = await chromium.launch({executablePath:process.env.QUEEZO_ROOM_BROWSER_EXECUTABLE,headless:true});
  try {
    const host = await browser.newContext({baseURL,viewport:{width:1340,height:900}});
    const guest = await browser.newContext({baseURL,viewport:{width:390,height:820}});
    host.setDefaultTimeout(20000);
    guest.setDefaultTimeout(20000);
    const suffix = require('node:crypto').randomUUID().slice(0,8);
    const aName = 'alice_' + suffix;
    const bName = 'bob_' + suffix;
    const [alice,bob] = await Promise.all([[host,aName,'Alice'],[guest,bName,'Bob']].map(([ctx,username,display_name]) =>
      call(ctx,'POST','/auth/signup',{display_name,username,email:username + '@example.com',password,confirm_password:password},null,201)));
    const hostToken = alice.csrf_token, guestToken = bob.csrf_token;
    await call(host,'POST','/friends/requests',{username:bName},hostToken,204);
    await call(guest,'POST','/friends/requests/' + aName + '/respond',{decision:'accept'},guestToken,204);
    for (let index = 1; index <= 4; index++) {
      const context = await browser.newContext({baseURL});
      try {
        const username = 'buddy_' + index + '_' + suffix;
        const buddy = await call(context,'POST','/auth/signup',{
          display_name:'Buddy ' + index,username,email:username + '@example.com',password,confirm_password:password,
        },null,201);
        await call(host,'POST','/friends/requests',{username},hostToken,204);
        await call(context,'POST','/friends/requests/' + aName + '/respond',{decision:'accept'},buddy.csrf_token,204);
      } finally { await context.close(); }
    }
    for (let index = 1; index <= 6; index++) {
      await call(host,'POST','/decks',{title:'Carousel deck ' + index},hostToken,201);
    }
    const deck = await call(host,'POST','/decks',{title:'Browser room deck'},hostToken,201);
    for (const name of ['Neptune','Venus','Mercury','Saturn']) {
      await call(host,'POST','/decks/' + deck.id + '/cards',{front:'Choose ' + name,back:name},hostToken,201);
    }
    const hostPage = await host.newPage();
    const guestPage = await guest.newPage();
    for (const page of [hostPage,guestPage]) {
      await page.addInitScript(() => {
        window.chatSounds = 0;
        window.studyPitches = [];
        if (!window.AudioContext) return;
        const start = OscillatorNode.prototype.start;
        OscillatorNode.prototype.start = function (...args) {
          const pitch = Math.round(this.frequency.value);
          if ([520,659,880,1109,247,185].includes(pitch)) window.studyPitches.push(pitch);
          else window.chatSounds++;
          return start.apply(this,args);
        };
      });
    }
    let frames = 0;
    for (const page of [hostPage,guestPage]) page.on('websocket', socket => {
      if (socket.url().endsWith('/live')) socket.on('framereceived', () => frames++);
    });

    const notificationsReady = new Promise(resolve => {
      guestPage.on('websocket', socket => {
        if (socket.url().endsWith('/rooms/notifications/live')) socket.on('framereceived',resolve);
      });
    });
    await guestPage.goto('/#/dashboard');
    await guestPage.getByRole('button',{name:'Open notifications'}).click();
    await notificationsReady;
    await guestPage.getByText('You’re all caught up').waitFor();
    await hostPage.goto('/#/dashboard');
    await hostPage.locator('#open-friends').click();
    await hostPage.locator('.friend-row summary').filter({hasText:'Bob'}).click();
    await hostPage.getByRole('button',{name:'Invite to Study'}).click();
    await hostPage.getByRole('heading',{name:'Lobby'}).waitFor();
    assert.equal(await hostPage.locator('.site-header').isVisible(),false);
    await hostPage.getByRole('heading',{name:"Alice's Room"}).waitFor();
    assert.equal(await hostPage.locator('.ambient-shapes').count(),1);
    assert.equal(await hostPage.locator('.room-study > .ambient-shapes').count(),1);
    await hostPage.emulateMedia({reducedMotion:'reduce'});
    assert.equal(await hostPage.locator('.ambient-shapes').isVisible(),false);
    await hostPage.emulateMedia({reducedMotion:'no-preference'});
    await guestPage.locator('.room-invite-count').filter({hasText:/^1$/}).waitFor({timeout:3500});
    await guestPage.getByRole('button',{name:'Accept',exact:true}).click();
    await guestPage.getByText('Waiting for all connected participants except the host to be ready.').waitFor();


    // Try the short phone layout and keyboard-only drawer navigation.
    const guestViewport = guestPage.viewportSize();
    await guestPage.setViewportSize({width:320,height:540});
    assert.ok(await guestPage.locator('.room-heading h1').evaluate(heading => {
      const title = heading.textContent;
      heading.textContent = 'W'.repeat(40) + "'s Room";
      const fits = heading.scrollWidth <= heading.clientWidth && document.documentElement.scrollWidth <= innerWidth;
      heading.textContent = title;
      return fits;
    }));
    const participantsToggle = guestPage.getByRole('button',{name:'Participants',exact:true});
    await participantsToggle.click();
    const participantsDrawer = guestPage.getByRole('dialog',{name:'Participants'});
    await participantsDrawer.waitFor();
    assert.equal(await guestPage.locator('.room-main').evaluate(main => main.inert),true);
    await guestPage.keyboard.press('Shift+Tab');
    assert.ok(await participantsDrawer.evaluate(panel => panel.contains(document.activeElement)));
    await guestPage.keyboard.press('Escape');
    assert.ok(await participantsToggle.evaluate(button => document.activeElement === button));
    await guestPage.setViewportSize(guestViewport);

    // Closing one of two tabs must leave the shared membership connected.
    const extraTab = await guest.newPage();
    const extraSync = new Promise(resolve => extraTab.on('websocket', socket => {
      if (socket.url().includes('/rooms/') && !socket.url().endsWith('/notifications/live')) {
        socket.once('framereceived',resolve);
      }
    }));
    await extraTab.goto(guestPage.url());
    await extraSync;
    await extraTab.close();
    const statePath = '/rooms/' + guestPage.url().split('/').at(-1);
    const roomRead = await call(guest,'GET',statePath,undefined,null,200);
    assert.ok(roomRead.participants.find(member => member.you).connected);
    const readTimes = [];
    for (let batch = 0; batch < 4; batch++) {
      const timings = await Promise.all([host,guest,guest].map(async context => {
        const start = performance.now();
        await call(context,'GET',statePath,undefined,null,200);
        return performance.now() - start;
      }));
      readTimes.push(...timings);
    }
    readTimes.sort((a,b) => a - b);
    console.log('Bounded room reads: 12 requests, 3 concurrent per batch, median ' +
      ((readTimes[5] + readTimes[6]) / 2).toFixed(1) + ' ms, max ' + readTimes.at(-1).toFixed(1) + ' ms.');

    assert.equal(await guestPage.getByRole('button',{name:'Select Browser room deck'}).count(),0);
    for (const page of [hostPage,guestPage]) {
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth &&
        document.documentElement.scrollHeight <= innerHeight),'Room fits the viewport');
    }
    const heading = await hostPage.locator('.room-heading').boundingBox();
    const study = await hostPage.locator('.room-study').boundingBox();
    const participants = await hostPage.locator('#room-participants').boundingBox();
    const chat = await hostPage.locator('#room-chat').boundingBox();
    assert.equal(heading.y,participants.y);
    assert.equal(heading.x,study.x);
    assert.equal(heading.width,study.width);
    assert.ok(Math.abs(study.y + study.height - chat.y - chat.height) < 1);
    await hostPage.locator('.room-invite-friends summary').click();
    await hostPage.getByRole('button',{name:'Already Joined · Bob'}).waitFor();
    await hostPage.getByRole('button',{name:'Next',exact:true}).click();
    await hostPage.getByRole('button',{name:'Invite · Buddy 4',exact:true}).click();
    await hostPage.getByRole('button',{name:'Invited · Buddy 4',exact:true}).waitFor();
    assert.equal(await hostPage.getByRole('button',{name:'Invited · Buddy 4',exact:true}).isDisabled(),true);
    await hostPage.getByRole('button',{name:'Previous',exact:true}).click();
    await hostPage.getByRole('button',{name:'Already Joined · Bob'}).waitFor();

    const waiting = await guestPage.locator('.room-guest-lobby').boundingBox();
    const guestStudy = await guestPage.locator('.room-study').boundingBox();
    assert.ok(Math.abs(waiting.y + waiting.height / 2 - guestStudy.y - guestStudy.height / 2) < 3);
    await guestPage.locator('.room-guest-lobby').getByRole('button',{name:'Ready',exact:true}).click();
    await hostPage.getByText('1 of 1 guests ready').waitFor();
    await guestPage.locator('.room-lobby-avatars .ready').getByText('Bob').waitFor();

    const nextDecks = hostPage.getByRole('button',{name:'Next decks'});
    await nextDecks.click();
    await hostPage.waitForFunction(() => document.querySelector('.room-deck-track').scrollLeft > 10);
    assert.equal(await hostPage.evaluate(() => scrollX + scrollY),0);
    const footer = await hostPage.locator('.room-lobby-footer').boundingBox();
    assert.ok(Math.abs(study.y + study.height - footer.y - footer.height) < 20);

    const deckOption = hostPage.getByRole('button',{name:'Select Browser room deck'});
    await deckOption.click();
    assert.equal(await deckOption.getAttribute('aria-pressed'),'true');
    await hostPage.getByLabel('Study mode').selectOption('challenge');
    assert.equal(await hostPage.getByRole('button',{name:'Save settings'}).count(),0);
    await hostPage.getByLabel('Seconds per question').fill('35');
    await guestPage.getByText('Challenge · 35 s per question').waitFor();
    await guestPage.locator('.room-deck-preview').getByRole('heading',{name:'Browser room deck'}).waitFor();
    await guestPage.getByText('The host updated the room settings. Readiness was reset.').waitFor();
    assert.equal(await hostPage.getByRole('button',{name:'Ready',exact:true}).count(),0);
    assert.equal(await hostPage.getByRole('button',{name:'Start study'}).isDisabled(),true);
    await hostPage.getByText('0 of 1 guests ready').waitFor();
    assert.equal(await guestPage.locator('#room-participants').getByRole('button',{name:'Ready',exact:true}).count(),0);
    await guestPage.locator('.room-guest-lobby').getByRole('button',{name:'Ready',exact:true}).click();
    await hostPage.getByRole('button',{name:'Start study'}).click();
    const starting = page => page.getByRole('timer',{name:'Study starts in'});
    await Promise.all([hostPage,guestPage].map(page => starting(page).filter({hasText:/^[1-5]$/}).waitFor({timeout:35000})));
    assert.equal(await hostPage.locator('.room-options button').count(),0);
    assert.equal(await guestPage.getByRole('timer',{name:'Time remaining'}).count(),0);
    for (const number of ['4','3','2','1']) {
      await starting(hostPage).filter({hasText:number}).waitFor({timeout:1600});
    }
    await hostPage.getByRole('heading',{name:'Question 1 of 4'}).waitFor({timeout:35000});
    await guestPage.getByRole('heading',{name:'Question 1 of 4'}).waitFor();
    const hostOptions = await hostPage.locator('.room-options .mc-option-text').allTextContents();
    assert.deepEqual(hostOptions,await guestPage.locator('.room-options .mc-option-text').allTextContents());
    assert.equal(hostOptions.length,4);
    const desktop = await hostPage.locator('.room-options button').evaluateAll(options => options.map(el => el.getBoundingClientRect().y));
    const mobile = await guestPage.locator('.room-options button').evaluateAll(options => options.map(el => el.getBoundingClientRect().y));
    assert.equal(new Set(desktop).size,1);
    assert.equal(new Set(mobile).size,4);
    assert.ok(await guestPage.evaluate(() => document.documentElement.scrollHeight <= innerHeight));
    await hostPage.getByRole('button',{name:'Enter Chat'}).click();
    const correctText = (await hostPage.locator('.room-question').innerText()).trim().replace(/^Choose /,'');
    const wrongText = hostOptions.find(option => option !== correctText);
    const guestWrong = guestPage.getByRole('button',{name:wrongText,exact:true});
    const hostCorrect = hostPage.getByRole('button',{name:correctText,exact:true});
    assert.equal(await hostPage.getByText('Answering',{exact:true}).count(),0);
    assert.equal(await hostPage.getByRole('button',{name:/^(Lock In|Submit Answer)$/}).count(),0);
    const hostChoiceBefore = await hostCorrect.boundingBox();
    const guestChoiceBefore = await guestWrong.boundingBox();
    const choiceAvatar = (page, choice, name) => page.locator('.room-answer')
      .filter({has:page.getByRole('button',{name:choice,exact:true})})
      .locator('.room-answer-avatars img[title="' + name + '"]');
    const ownAvatar = choiceAvatar(guestPage,wrongText,'Bob');
    const guestTextBefore = await guestWrong.locator('.mc-option-text').boundingBox();
    await guestWrong.click();
    await ownAvatar.waitFor();
    await guestPage.waitForFunction(() => window.studyPitches.includes(520));
    const avatarBox = await ownAvatar.boundingBox();
    assert.equal(avatarBox.width,32);
    assert.ok(avatarBox.y + avatarBox.height <= guestChoiceBefore.y);
    assert.equal(await guestWrong.locator("img").count(),0);
    assert.deepEqual(await guestWrong.locator(".mc-option-text").boundingBox(),guestTextBefore);
    assert.equal(await hostPage.locator('.room-answer-avatars img').count(),0);
    assert.equal(await guestPage.getByText('Answer locked. Waiting for other participants.').count(),0);
    assert.deepEqual(await guestWrong.boundingBox(),guestChoiceBefore);
    assert.equal(await guestWrong.isDisabled(),true);
    const reviewClock = page => page.getByRole('timer',{name:'Seconds until next question'});
    assert.equal(await reviewClock(hostPage).count(),0);
    assert.equal(await reviewClock(guestPage).count(),0);
    assert.equal(await guestWrong.evaluate(async option => {
      await Promise.all(option.getAnimations().map(animation => animation.finished));
      return getComputedStyle(option).backgroundColor;
    }),'rgb(237, 245, 255)');
    await guestPage.getByRole('button',{name:'Chat',exact:true}).click();
    assert.equal(await guestPage.getByRole('textbox',{name:'Chat message'}).count(),0);
    await guestPage.getByRole('button',{name:'Enter Chat'}).click();
    await guestPage.getByRole('textbox',{name:'Chat message'}).fill('Test room chat');
    await guestPage.getByRole('button',{name:'Send',exact:true}).click();
    await hostPage.getByText('Test room chat').waitFor();
    await hostPage.waitForFunction(() => window.chatSounds === 1);
    assert.equal(await guestPage.evaluate(() => window.chatSounds),0);
    await hostPage.getByRole('button',{name:'Mute',exact:true}).click();
    await guestPage.getByRole('textbox',{name:'Chat message'}).fill('Muted message');
    await guestPage.getByRole('button',{name:'Send',exact:true}).click();
    await hostPage.getByText('Muted message').waitFor();
    assert.equal(await hostPage.evaluate(() => window.chatSounds),1);
    await guestPage.getByRole('button',{name:'Close chat'}).click();
    assert.equal(await guestWrong.getAttribute('aria-pressed'),'true');
    await ownAvatar.waitFor();
    await guestPage.reload();
    await guestPage.getByRole('button',{name:'Chat',exact:true}).click();
    assert.equal(await guestPage.getByRole('button',{name:'Enter Chat'}).count(),0);
    await guestPage.getByText('Test room chat').waitFor();
    assert.equal(await guestPage.evaluate(() => window.chatSounds),0);
    await guestPage.getByRole('button',{name:'Close chat'}).click();
    await ownAvatar.waitFor();
    assert.deepEqual(await guestPage.evaluate(() => window.studyPitches),[]);
    await hostCorrect.click();
    await Promise.all([hostPage,guestPage].map(page => reviewClock(page).filter({hasText:/^[1-5]$/}).waitFor()));
    const firstReviewNumber = await reviewClock(hostPage).innerText();
    await choiceAvatar(hostPage,correctText,'Alice').waitFor();
    await choiceAvatar(hostPage,wrongText,'Bob').waitFor();
    await choiceAvatar(guestPage,correctText,'Alice').waitFor();
    assert.deepEqual(await hostCorrect.boundingBox(),hostChoiceBefore);
    assert.deepEqual(await guestWrong.boundingBox(),guestChoiceBefore);
    assert.equal(await hostPage.locator('#room-participants').getByText(/^(Answered|Connected)$/).count(),0);
    const guestCorrect = guestPage.getByRole('button',{name:correctText,exact:true});
    const revealBorder = option => option.evaluate(async element => {
      await Promise.all(element.getAnimations().map(animation => animation.finished));
      return getComputedStyle(element).borderColor;
    });
    assert.equal(await revealBorder(guestCorrect),'rgb(168, 213, 182)');
    assert.equal(await revealBorder(guestWrong),'rgb(235, 193, 187)');
    await hostPage.waitForFunction(() => window.studyPitches.length === 4);
    assert.deepEqual(await hostPage.evaluate(() => window.studyPitches),[520,659,880,1109]);
    await reviewClock(hostPage).filter({hasNotText:firstReviewNumber}).waitFor({timeout:1600});
    await hostPage.getByRole('heading',{name:'Question 2 of 4'}).waitFor();
    assert.equal(await reviewClock(hostPage).count(),0);
    assert.equal(await hostPage.locator('.room-options .mc-incorrect').count(),0);
    assert.ok(frames > 3,'WebSocket frames received through Nginx');
    const leaveDialog = page => page.getByRole('dialog',{name:'Leave study room?'});
    const confirmLeave = page => leaveDialog(page).getByRole('button',{name:'Leave Room',exact:true});
    await guestPage.getByRole('button',{name:'Leave Room',exact:true}).click();
    assert.ok(await confirmLeave(guestPage).evaluate(button => button.classList.contains('danger')));
    await leaveDialog(guestPage).getByRole('button',{name:'Cancel',exact:true}).click();
    await hostPage.getByRole('button',{name:'Leave Room',exact:true}).click();
    assert.equal(await leaveDialog(hostPage).locator('select, input[type=radio]').count(),0);
    await confirmLeave(hostPage).click();
    await hostPage.getByRole('heading',{name:'Home',exact:true}).waitFor();
    await guestPage.getByRole('button',{name:'Participants',exact:true}).click();
    await guestPage.locator('#room-participants').getByText('Host',{exact:true}).waitFor();
    await guestPage.getByRole('button',{name:'Close participants'}).click();
    await guestPage.getByRole('heading',{name:"Bob's Room"}).waitFor();
    await guestPage.getByRole('button',{name:'Leave Room',exact:true}).click();
    await confirmLeave(guestPage).click();
    await guestPage.getByRole('heading',{name:'Home',exact:true}).waitFor();

    // The room filled the cache while the deck was private. Publishing keeps its choices.
    const publication = await call(host,'PATCH','/decks/' + deck.id,{visibility:'public'},hostToken,200);
    const sharedUrl = '/#/shared/' + publication.share_token;
    await guestPage.goto(sharedUrl);
    await guestPage.getByRole('button',{name:'Study',exact:true}).click();
    await guestPage.getByRole('radio',{name:/Multiple-Choice Mode/}).check();
    await guestPage.getByRole('button',{name:'Start studying',exact:true}).click();
    await guestPage.waitForURL('**/multiple-choice/**');
    await guestPage.locator('.mc-option').first().waitFor();
    assert.equal(await guestPage.locator('.mc-option').count(),4);
    await guestPage.getByRole('link',{name:'Return to deck',exact:true}).first().click();
    await guestPage.waitForURL('**' + sharedUrl);
    await guestPage.goto(sharedUrl + '/study?type=multiple-choice');
    await guestPage.waitForURL('**/multiple-choice/**');
    await guestPage.locator('.mc-option').first().waitFor();
    console.log('Two-browser Compose check passed: invitation, private-deck consent, synchronized fallback questions, mobile chat, synchronized start and review timers, lock and correct sounds, shared reveal avatars and colors, stable choice positions, refresh recovery, host transfer, and cached shared-deck solo practice.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
