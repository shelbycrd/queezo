const assert = require('node:assert/strict');
const {chromium} = require(process.env.QUEEZO_PLAYWRIGHT || 'playwright');

// Run only against the disposable site described in docs/STUDY_ROOMS.md.
const baseURL = process.env.QUEEZO_ROOM_TEST_URL || 'http://127.0.0.1:18711';
const password = 'A disposable room test passphrase';
async function call(context, method, path, data, csrf, expected) {
  const response = await context.request.fetch('/api' + path,{
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
    const deck = await call(host,'POST','/decks',{title:'Browser room deck'},hostToken,201);
    for (const name of ['Neptune','Venus','Mercury','Saturn']) {
      await call(host,'POST','/decks/' + deck.id + '/cards',{front:'Choose ' + name,back:name},hostToken,201);
    }
    const hostPage = await host.newPage();
    const guestPage = await guest.newPage();
    let frames = 0;
    for (const page of [hostPage,guestPage]) page.on('websocket', socket => {
      if (socket.url().endsWith('/live')) socket.on('framereceived', () => frames++);
    });

    await hostPage.goto('/#/dashboard');
    await hostPage.getByRole('button',{name:'Open friends'}).click();
    await hostPage.locator('.friend-row summary').click();
    await hostPage.getByRole('button',{name:'Invite to Study'}).click();
    await hostPage.getByRole('heading',{name:'Lobby'}).waitFor();
    assert.equal(await hostPage.locator('.site-header').isVisible(),false);
    await guestPage.goto('/#/dashboard');
    await guestPage.getByRole('button',{name:'Open notifications'}).click();
    await guestPage.getByRole('button',{name:'Accept',exact:true}).click();
    await guestPage.getByRole('heading',{name:'Lobby'}).waitFor();

    await hostPage.getByLabel('Study deck').selectOption(String(deck.id));
    await hostPage.getByLabel('Allow invited room members to study this deck').check();
    await hostPage.getByLabel('Study mode').selectOption('challenge');
    await hostPage.getByRole('button',{name:'Save settings'}).click();
    await guestPage.getByText('Browser room deck · 4 questions').waitFor();
    await guestPage.getByRole('button',{name:'Ready',exact:true}).click();
    await hostPage.getByRole('button',{name:'Start study'}).click();
    await hostPage.getByRole('heading',{name:'Question 1 of 4'}).waitFor({timeout:35000});
    await guestPage.getByRole('heading',{name:'Question 1 of 4'}).waitFor();
    const hostOptions = await hostPage.locator('.room-options button').allTextContents();
    assert.deepEqual(hostOptions,await guestPage.locator('.room-options button').allTextContents());
    assert.equal(hostOptions.length,4);
    await guestPage.locator('.room-options button').first().click();
    await guestPage.getByRole('button',{name:'Chat',exact:true}).click();
    await guestPage.getByRole('textbox',{name:'Chat message'}).fill('Test room chat');
    await guestPage.getByRole('button',{name:'Send',exact:true}).click();
    await hostPage.getByText('Test room chat',{exact:true}).waitFor();
    await guestPage.getByRole('button',{name:'Close chat'}).click();
    assert.equal(await guestPage.locator('.room-options button').first().getAttribute('aria-pressed'),'true');
    await guestPage.getByRole('button',{name:'Lock In'}).click();
    await guestPage.getByText('Answer locked. Waiting for other participants.').waitFor();
    await guestPage.reload();
    await guestPage.getByText('Answer locked. Waiting for other participants.').waitFor();
    await hostPage.locator('.room-options button').first().click();
    await hostPage.getByRole('button',{name:'Lock In'}).click();
    await hostPage.getByRole('list',{name:'Round leaderboard'}).waitFor();
    await guestPage.getByRole('list',{name:'Round leaderboard'}).waitFor();
    assert.ok(frames > 3,'WebSocket frames received through Nginx');
    await hostPage.getByRole('button',{name:'Leave',exact:true}).click();
    await hostPage.getByRole('button',{name:'Continue',exact:true}).click();
    await hostPage.getByLabel('New host').selectOption(bName);
    await hostPage.getByRole('button',{name:'Transfer and leave',exact:true}).click();
    await hostPage.getByRole('heading',{name:'Home',exact:true}).waitFor();
    await guestPage.getByRole('button',{name:'Participants',exact:true}).click();
    await guestPage.locator('#room-participants').getByText(/^Host/).waitFor();
    await guestPage.getByRole('button',{name:'Close participants'}).click();
    await guestPage.getByRole('button',{name:'Leave',exact:true}).click();
    await guestPage.getByRole('button',{name:'Continue',exact:true}).click();
    await guestPage.getByRole('radio',{name:'End Room',exact:true}).check();
    await guestPage.getByRole('button',{name:'End Room',exact:true}).click();
    await guestPage.getByRole('heading',{name:'Home',exact:true}).waitFor();
    console.log('Two-browser Compose check passed: invitation, private-deck consent, synchronized fallback questions, mobile chat, preserved selection, Challenge lock-in, refresh recovery, leaderboard, and host transfer.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
