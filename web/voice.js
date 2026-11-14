// Owner: P1. ElevenLabs voice agent "Traceback On-Call" (plan 6.4, P1-8).
// Client tools run here in the page and call OUR API with window.traceback.currentKey():
//   start_case(case_id)       POST /incidents + POST /incidents/{id}/runs, then window.traceback.showRun(runId)
//   get_run_status(run_id)    GET /runs/{id}            -> metadata only
//   find_memories(symptom)    GET /memories/search?q=   -> count, owner team, status, expiry; never memory text
// No ElevenLabs API key ever goes in web/. Forget is never done by voice.
(function () {
  if (!window.traceback) return;
  // TODO(P1-8): load @elevenlabs/client, startSession with ELEVENLABS_AGENT_ID and clientTools.
})();
