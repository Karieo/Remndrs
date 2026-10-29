# SMS and voice sender authorization

Prepared change; not deployed. Provider signature verification stays mandatory.
A valid Twilio signature proves the request came through Twilio, not that the
human caller may read your notes.

Each user's Settings → profile needs:
- **Remndrs #**: their dedicated Twilio destination number.
- **Phone**: the personal number authorized to send commands or call that number.

Both must include an explicit `+` country code. Spaces, parentheses, periods
and hyphens are ignored for comparison. No country is guessed for local-only
numbers. Anonymous/short-code/malformed/missing callers are rejected. Exactly
one user must own the normalized destination; duplicates fail closed rather
than selecting an arbitrary user's private notes. Multiple authorized senders
per user are not introduced by this change.

The initial OWNER_PHONE_NUMBER environment value seeds a new owner only;
changing it does not repair an existing user's stored profile. Confirm existing
profile configuration privately before enabling inbound SMS/voice. Do not paste
numbers, tokens or recovery notes into review artifacts.

The gate runs before SMS LIST/GET/FIND, reminder or note creation, and before
voice recording and transcription. Rejected configured requests return 403
without revealing whether a destination or sender matched. When Twilio is
unconfigured, the existing no-op SMS behavior remains.

## Verification and rollout

Unit tests use fake provider keys, synthetic users/notes and Flask's local test
client; no real SMS is sent. They cover validly signed unauthorized senders,
missing/malformed callers, destination mismatch/duplicates, absent configured
personal number, display formatting, bad signatures and authorized SMS/voice.

Before a production rollout (separate approval required):
1. Take and verify a recoverable backup using the actual deployment paths.
2. Check the current deployed revision and privately verify destination/personal
   number mapping; no account-data migration is required.
3. Deploy the reviewed commit only with authorization and check app health plus
   existing non-provider auth flows. Any real SMS/voice test needs separate
   explicit approval and must use harmless synthetic text, never recovery data.
4. Watch provider response failures without logging full request bodies, raw
   secrets or private note contents.

If legitimate traffic is denied, keep the gate in place and correct the user's
profile mapping. Prefer disabling inbound integrations while diagnosing rather
than rolling back the authorization fix. Restoring old app code reopens the
known privacy gap; do not do it silently. No schema changes accompany this fix.

## Recording callback binding and deployment limits

Twilio's [Record recordingStatusCallback contract](https://www.twilio.com/docs/voice/twiml/record)
provides CallSid/recording metadata, not a guaranteed From/To pair. The previous
handler depended on those phone fields and could silently skip such callbacks.
The prepared handler instead puts a short-lived signed context on the callback
URL after authorizing the initial answer request. It binds user, CallSid and a
hash of the current personal/destination-number configuration using the app's
existing secret. The callback requires BOTH Twilio signature and that context,
matching CallSid, completed recording status, unchanged profile and a still
unique/authorized destination. No Twilio account lookup is added.

Contexts expire after 15 minutes and are held in a bounded in-process map,
matching the existing single-process threaded Flask deployment. The same answer
retry reuses its context. Concurrent processing is rejected; successful callback
retries return success without duplicate notes or SMS. Failures before note
creation may retry; failures after note insertion mark the context consumed to
avoid duplicate notes, and require checking/repairing mirror or notification
work. The existing exception is logged, never the context or note contents by
new code.

This is NOT distributed or durable job processing. Restart, multiple processes,
or callbacks delayed beyond 15 minutes fail closed; a user may have to re-record.
Do not deploy this design to a multi-worker server without shared durable
idempotency/context storage and tests. The callback query context must be
redacted from proxy/access logs before production use; it is short-lived,
call-bound, one-use and not a general application bearer token. No phone numbers
are embedded in it. Existing recordings are not queried or migrated.

Tests include provider-signed callbacks with the documented no-From/To shape,
tampering, expiration, mismatched calls, profile changes, lost process state,
concurrent/repeated delivery and preserved authorized behavior using fake audio.
