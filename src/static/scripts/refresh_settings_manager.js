/**
 * refresh_settings_manager.js
 * Factory for managing a refresh settings modal form.
 * Usage: createRefreshSettingsManager(modalId, prefix) → manager
 *   manager.open({ refreshSettings }) – populate & show the modal
 *   manager.submit(asyncCallback)     – validate, call callback(formData), handle errors
 */
(function () {
  /**
   * @param {string} modalId  - ID of the modal container element
   * @param {string} prefix   - Prefix used for form element IDs inside the modal
   */
  window.createRefreshSettingsManager = function (modalId, prefix) {
    var modal = document.getElementById(modalId);

    function getEl(id) {
      return document.getElementById(prefix + '-' + id);
    }

    /**
     * Populate form fields from a refreshSettings object and show the modal.
     * @param {Object} opts
     * @param {Object} opts.refreshSettings - { refreshType, interval, unit, refreshTime }
     */
    function open(opts) {
      var settings = (opts && opts.refreshSettings) ? opts.refreshSettings : {};

      var radioInterval  = getEl('refresh-interval');
      var radioScheduled = getEl('refresh-scheduled');
      var inputInterval  = getEl('interval');
      var selectUnit     = getEl('unit');
      var inputScheduled = getEl('scheduled');

      // Populate interval fields
      if (inputInterval && settings.interval) inputInterval.value = settings.interval;
      if (selectUnit && settings.unit)        selectUnit.value     = settings.unit;
      if (inputScheduled && settings.refreshTime) inputScheduled.value = settings.refreshTime;

      // Select the right radio
      var type = settings.refreshType || 'interval';
      if (type === 'scheduled' && radioScheduled) {
        radioScheduled.checked = true;
      } else if (radioInterval) {
        radioInterval.checked = true;
      }

      if (modal) modal.style.display = 'block';
    }

    /**
     * Validate the form, collect data, and call the async callback.
     * @param {Function} asyncCallback - called with formData object on valid submit
     */
    async function submit(asyncCallback) {
      var radioInterval  = getEl('refresh-interval');
      var radioScheduled = getEl('refresh-scheduled');
      var inputInterval  = getEl('interval');
      var selectUnit     = getEl('unit');
      var inputScheduled = getEl('scheduled');

      var isInterval  = radioInterval  && radioInterval.checked;
      var isScheduled = radioScheduled && radioScheduled.checked;

      // Validate
      if (isInterval) {
        var val = parseFloat(inputInterval ? inputInterval.value : '');
        if (!val || val <= 0) {
          alert('Please enter a valid refresh interval.');
          return;
        }
      } else if (isScheduled) {
        if (!inputScheduled || !inputScheduled.value) {
          alert('Please select a scheduled refresh time.');
          return;
        }
      } else {
        alert('Please select a refresh type.');
        return;
      }

      // Collect
      var formData = {
        refreshType: isInterval ? 'interval' : 'scheduled',
        interval:    inputInterval  ? inputInterval.value  : '',
        unit:        selectUnit     ? selectUnit.value     : 'minute',
        refreshTime: inputScheduled ? inputScheduled.value : ''
      };

      try {
        await asyncCallback(formData);
        if (modal) modal.style.display = 'none';
      } catch (err) {
        console.error('Refresh settings submit error:', err);
        if (window.showResponseModal) {
          showResponseModal('failure', 'Error: ' + (err.message || 'Failed to save refresh settings.'));
        } else {
          alert('Error: ' + (err.message || 'Failed to save refresh settings.'));
        }
      }
    }

    // Close when clicking outside modal content
    if (modal) {
      modal.addEventListener('click', function (e) {
        if (e.target === modal) modal.style.display = 'none';
      });
    }

    return { open: open, submit: submit };
  };
})();
