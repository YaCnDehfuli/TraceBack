// Owner: P2. The memory card, Fence split view and admin drawer (plan 7.3, P2-4 / P2-5 / P2-7).
// Implements window.traceback.renderMemoryCard(memory, context): memory is a MemoryCard (contracts/models.py),
// context carries the current identity and, during a run, the condition results for this incident.
// Show "match: strong/weak", never a raw score; IDs, versions and hashes go behind "details".
(function () {
  if (!window.traceback) return;
  window.traceback.renderMemoryCard = function (memory, context) {
    const div = document.createElement("div");
    div.textContent = memory && memory.title ? memory.title : "(memory card: TODO P2-4)";
    return div;
  };
})();
