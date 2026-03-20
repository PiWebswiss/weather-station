/**
 * response_modal.js
 * Handles the reusable success/failure notification modal (#responseModal).
 * Requires response_modal.html to be included in the page.
 */
(function () {
  var _autoCloseTimer = null;

  /**
   * Show the response modal.
   * @param {string} type    - 'success' or 'failure'
   * @param {string} message - Message to display inside the modal
   * @param {number} [autoCloseMs=4000] - Auto-close delay in ms (0 = no auto-close)
   */
  window.showResponseModal = function (type, message, autoCloseMs) {
    var modal = document.getElementById('responseModal');
    var content = document.getElementById('modalContent');
    var msg = document.getElementById('modalMessage');
    if (!modal || !content || !msg) return;

    // Set message
    msg.textContent = message;

    // Toggle success/failure styling
    content.classList.remove('success', 'failure');
    content.classList.add(type === 'success' ? 'success' : 'failure');

    // Show
    modal.style.display = 'flex';

    // Auto-close
    if (_autoCloseTimer) clearTimeout(_autoCloseTimer);
    var delay = (autoCloseMs === undefined) ? 4000 : autoCloseMs;
    if (delay > 0) {
      _autoCloseTimer = setTimeout(function () {
        closeResponseModal();
      }, delay);
    }
  };

  /**
   * Close the response modal.
   */
  window.closeResponseModal = function () {
    var modal = document.getElementById('responseModal');
    if (modal) modal.style.display = 'none';
    if (_autoCloseTimer) {
      clearTimeout(_autoCloseTimer);
      _autoCloseTimer = null;
    }
  };

  // Close when clicking outside modal content
  document.addEventListener('DOMContentLoaded', function () {
    var modal = document.getElementById('responseModal');
    if (modal) {
      modal.addEventListener('click', function (e) {
        if (e.target === modal) closeResponseModal();
      });
    }
  });
})();
