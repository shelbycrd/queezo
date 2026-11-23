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
        if (!window.AudioContext) return;
        const create = AudioContext.prototype.createOscillator;
        AudioContext.prototype.createOscillator = function () {
          window.chatSounds++;
          return create.call(this);
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
    await hostPage.getByRole('button',{name:'Open friends'}).click();
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

    assert.equal(await guestPage.getByRole('button',{name:'Select Browser room deck'}).count(),0);
    for (const page of [hostPage,guestPage]) {
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth &&
        document.documentElement.scrollHeight <= innerHeight),'Room fits the viewport');
    }
    const study = await hostPage.locator('.room-study').boundingBox();
    const participants = await hostPage.locator('#room-participants').boundingBox();
    const chat = await hostPage.locator('#room-chat').boundingBox();
    assert.equal(study.y,participants.y);
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
    await hostPage.getByRole('heading',{name:'Question 1 of 4'}).waitFor({timeout:35000});
    await guestPage.getByRole('heading',{name:'Question 1 of 4'}).waitFor();
    const hostOptions = await hostPage.locator('.room-options button').allTextContents();
    assert.deepEqual(hostOptions,await guestPage.locator('.room-options button').allTextContents());
    assert.equal(hostOptions.length,4);
    const desktop = await hostPage.locator('.room-options button').evaluateAll(options => options.map(el => el.getBoundingClientRect().y));
    const mobile = await guestPage.locator('.room-options button').evaluateAll(options => options.map(el => el.getBoundingClientRect().y));
    assert.equal(new Set(desktop).size,1);
    assert.equal(new Set(mobile).size,4);
    assert.ok(await guestPage.evaluate(() => document.documentElement.scrollHeight <= innerHeight));
    await hostPage.getByRole('button',{name:'Enter Chat'}).click();
    await guestPage.locator('.room-options button').first().click();
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
    assert.equal(await guestPage.locator('.room-options button').first().getAttribute('aria-pressed'),'true');
    await guestPage.getByRole('button',{name:'Lock In'}).click();
    await guestPage.getByText('Answer locked. Waiting for other participants.').waitFor();
    await guestPage.reload();
    await guestPage.getByRole('button',{name:'Chat',exact:true}).click();
    assert.equal(await guestPage.getByRole('button',{name:'Enter Chat'}).count(),0);
    await guestPage.getByText('Test room chat').waitFor();
    assert.equal(await guestPage.evaluate(() => window.chatSounds),0);
    await guestPage.getByRole('button',{name:'Close chat'}).click();
    await guestPage.getByText('Answer locked. Waiting for other participants.').waitFor();
    await hostPage.locator('.room-options button').first().click();
    await hostPage.getByRole('button',{name:'Lock In'}).click();
    await hostPage.getByRole('list',{name:'Round leaderboard'}).waitFor();
    await guestPage.getByRole('list',{name:'Round leaderboard'}).waitFor();
    assert.ok(frames > 3,'WebSocket frames received through Nginx');
    await hostPage.getByRole('button',{name:'Leave Room',exact:true}).click();
    await hostPage.getByRole('button',{name:'Continue',exact:true}).click();
    await hostPage.getByLabel('New host').selectOption(bName);
    await hostPage.getByRole('button',{name:'Transfer and leave',exact:true}).click();
    await hostPage.getByRole('heading',{name:'Home',exact:true}).waitFor();
    await guestPage.getByRole('button',{name:'Participants',exact:true}).click();
    await guestPage.locator('#room-participants').getByText('Host',{exact:true}).waitFor();
    await guestPage.getByRole('heading',{name:"Bob's Room"}).waitFor();
    await guestPage.getByRole('button',{name:'Close participants'}).click();
    await guestPage.getByRole('button',{name:'Leave Room',exact:true}).click();
    await guestPage.getByRole('button',{name:'Continue',exact:true}).click();
    await guestPage.getByRole('radio',{name:'End Room',exact:true}).check();
    await guestPage.getByRole('button',{name:'End Room',exact:true}).click();
    await guestPage.getByRole('heading',{name:'Home',exact:true}).waitFor();
    console.log('Two-browser Compose check passed: invitation, private-deck consent, synchronized fallback questions, mobile chat, preserved selection, Challenge lock-in, refresh recovery, leaderboard, and host transfer.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
