import {test} from 'node:test';
import assert from 'node:assert/strict';
import {accuracy,arrivedInvites,remainingSeconds,roomSocketUrl} from '../src/services/rooms.js';

test('room sockets preserve the origin and use encrypted transport on HTTPS', () => {
  assert.equal(roomSocketUrl('room','https://example.test/u/name'),'wss://example.test/api/rooms/room/live');
  assert.equal(roomSocketUrl('room','http://localhost:5173'),'ws://localhost:5173/api/rooms/room/live');
});

test('room countdown rounds up and never reports negative time', () => {
  const deadline = '2026-11-23T12:00:30Z';
  assert.equal(remainingSeconds(deadline,Date.parse('2026-11-23T12:00:00.010Z')),30);
  assert.equal(remainingSeconds(deadline,Date.parse('2026-11-23T12:01:00Z')),0);
  assert.equal(remainingSeconds(null,Date.now()),null);
});

test('room accuracy uses the number of rounds, including unanswered rounds', () => {
  assert.equal(accuracy({correct:2,questions:3}),67);
  assert.equal(accuracy({correct:0,questions:0}),0);
});

test('only invitations missing from the previous snapshot trigger the popup', () => {
  const invites = [{room_id:'new'},{room_id:'old'}];
  assert.deepEqual(arrivedInvites(new Set(['old']),invites).map(invite => invite.room_id),['new']);
  assert.deepEqual(arrivedInvites(new Set(['old','new']),invites),[]);
  assert.deepEqual(arrivedInvites(new Set(['gone']),[]),[]);
});
