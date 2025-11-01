// static/js/video_manager.js

// IMPORTANT: This PAGE_DATA object is defined globally in the HTML template
// before this script is loaded.
/* Example structure:
const PAGE_DATA = {
    dailyLimit: 20, // or Infinity if -1 was passed from Python
    editsUsedToday: 5,
    userPlan: "creator",
    videos: [ {id: '...', title: '...', ...}, ... ]
};
*/

function videoManager() {
    return {
        // --- Initialize videos from PAGE_DATA ---
        videos: [], // Initialize as empty, will be populated in init()

        // State variables
        filter: 'all',
        sortBy: 'newest',
        selectedVideos: [],
        showBulkEditModal: false,
        showConfirmModal: false,
        bulkEditData: { tags_to_add: '', tags_to_remove: '', description_append: '', privacy_status: '' },
        isBulkUpdating: false,
        disclaimerChecked: false,
        bulkEditMode: false,

        // Limit variables
        userPlan: 'free',
        dailyLimit: 0,    // Will be set in init (Infinity for unlimited)
        editsUsedToday: 0, // Will be set in init
        remainingEdits: 0, // Will be calculated
        limitMessage: "",  // Message to display when limit prevents selection
        isIndeterminate: false, // For the "Select All" checkbox state

        init() {
            // Get data injected from Python via PAGE_DATA global constant
            if (typeof PAGE_DATA !== 'undefined') {
                // Load videos from PAGE_DATA
                this.videos = PAGE_DATA.videos || [];

                // Load limits and usage data
                this.dailyLimit = parseInt(PAGE_DATA.dailyLimit);
                // Handle invalid numbers, allow Infinity representation (formerly -1)
                if (isNaN(this.dailyLimit) || (this.dailyLimit < 0 && this.dailyLimit !== -1)) {
                   console.warn("Invalid dailyLimit received, defaulting to 0.");
                   this.dailyLimit = 0;
                }
                // Convert -1 from Python to Infinity for JS logic
                if (this.dailyLimit === -1) {
                    this.dailyLimit = Infinity;
                }

                this.editsUsedToday = parseInt(PAGE_DATA.editsUsedToday) || 0;
                this.userPlan = PAGE_DATA.userPlan || 'free';
            } else {
                console.error("PAGE_DATA is not defined. Bulk edit limits and video list might not work correctly.");
                this.videos = []; // Ensure videos is an empty array if PAGE_DATA is missing
                this.dailyLimit = 0; // Default to 0 if data is missing
            }
            this.calculateRemaining();
            this.checkSelectionLimit(); // Initial check

            // Watchers
            this.$watch('selectedVideos', () => {
                // Recalculate remaining based on CURRENT selection vs TODAY's usage
                this.calculateRemainingBasedOnSelection();
                this.updateIndeterminateState();
                // Check selection limit after state update
                // this.checkSelectionLimit(); // Let handleCardClick/toggleSelectAll manage trimming
            });

             // Watcher for bulkEditMode
             this.$watch('bulkEditMode', (newValue) => {
                if (!newValue) { // When exiting bulk edit mode
                    this.limitMessage = ""; // Clear limit message
                    this.isIndeterminate = false; // Reset checkbox state
                    // Selection is cleared in toggleBulkEditMode
                } else {
                     // When entering bulk edit mode, recalculate remaining based on initial state
                     this.calculateRemaining();
                }
             });
        },

        // Calculate how many MORE edits are possible today (limit - usedToday)
        calculateRemaining() {
            if (this.dailyLimit === Infinity) {
                this.remainingEdits = Infinity;
            } else {
                // Remaining edits allowed today, independent of current selection
                this.remainingEdits = Math.max(0, this.dailyLimit - this.editsUsedToday);
            }
        },

        // Calculate remaining based on current selection for immediate feedback
        calculateRemainingBasedOnSelection() {
             if (this.dailyLimit === Infinity) {
                 this.remainingEdits = Infinity;
             } else {
                 // Remaining slots considering what's already used today AND currently selected
                 // This might be confusing, let's stick to showing remaining for the DAY
                 this.remainingEdits = Math.max(0, this.dailyLimit - this.editsUsedToday);
             }
        },


        // Generate the limit message
        getLimitMessage() {
            if (this.dailyLimit === Infinity) return "";
            const limitVal = this.dailyLimit;
            // Show remaining slots for the day
            const edits_remaining_today = Math.max(0, this.dailyLimit - this.editsUsedToday);
            return `You can select ${edits_remaining_today} more videos today (${this.editsUsedToday}/${limitVal} used for ${this.userPlan.charAt(0).toUpperCase() + this.userPlan.slice(1)} plan).`;
        },

        // Prevent selection exceeding limit and update message
        checkSelectionLimit() {
            const currentSelectionCount = this.selectedVideos.length;
            // How many more *could* be selected based on remaining allowance *today*
            const canSelectCount = (this.dailyLimit === Infinity) ? Infinity : Math.max(0, this.dailyLimit - this.editsUsedToday);

            // This function seems designed to *trim* the selection, which might be unexpected.
            // Let's rely on the disabling logic and handleCardClick checks instead of auto-trimming.
            /*
            if (currentSelectionCount > canSelectCount) {
                this.selectedVideos.splice(canSelectCount); // Trim excess selection
                this.limitMessage = `Selection limited to ${canSelectCount} videos based on your daily limit.`;
                setTimeout(() => this.limitMessage = "", 3000);
            }
            */
            this.updateIndeterminateState(); // Just update checkbox state
        },

        // Update indeterminate state of the "Select All" checkbox
         updateIndeterminateState() {
             const visibleIds = this.filteredAndSortedVideos.map(v => v.id);
             const selectedVisibleCount = visibleIds.filter(id => this.selectedVideos.includes(id)).length;

             if (visibleIds.length === 0 || !this.bulkEditMode) {
                 this.isIndeterminate = false;
                 return;
             }

             // How many *more* videos can be selected today?
             const canSelectMore = (this.dailyLimit === Infinity) ? Infinity : Math.max(0, this.dailyLimit - this.editsUsedToday - this.selectedVideos.length + selectedVisibleCount);
             // How many total visible items *could* be selected?
             const totalSelectableVisible = Math.min(visibleIds.length, selectedVisibleCount + canSelectMore);

             if (selectedVisibleCount === 0) {
                 this.isIndeterminate = false; // Nothing selected
             } else if (selectedVisibleCount >= totalSelectableVisible && visibleIds.length === totalSelectableVisible) {
                 // Only truly 'checked' if all visible items could be and are selected
                  this.isIndeterminate = false;
             }
              else if (selectedVisibleCount > 0 && selectedVisibleCount < visibleIds.length) {
                 this.isIndeterminate = true; // Partially selected among visible
             }
             else {
                  this.isIndeterminate = false; // Covers case where selectedVisibleCount == visibleIds.length but maybe limit was hit
             }
        },


        get isAllSelected() {
            const visibleIds = this.filteredAndSortedVideos.map(v => v.id);
            if (visibleIds.length === 0 || !this.bulkEditMode) return false;

            // How many more videos *could* be added today from the visible ones?
            const canSelectMore = (this.dailyLimit === Infinity) ? Infinity : Math.max(0, this.dailyLimit - this.editsUsedToday - (this.selectedVideos.length - visibleIds.filter(id => this.selectedVideos.includes(id)).length));
            const selectableVisibleCount = Math.min(visibleIds.length, canSelectMore + visibleIds.filter(id => this.selectedVideos.includes(id)).length);

            // Check if all selectable visible videos *are* selected
            const selectedVisibleCount = visibleIds.filter(id => this.selectedVideos.includes(id)).length;

            return selectedVisibleCount >= selectableVisibleCount && selectableVisibleCount > 0;
        },


        get filteredAndSortedVideos() {
            // Ensure this.videos is an array before filtering/sorting
            if (!Array.isArray(this.videos)) {
                 console.error("this.videos is not an array:", this.videos);
                 return [];
            }
             let filtered = [...this.videos];
            if (this.filter === 'shorts') {
                filtered = filtered.filter(v => v.is_short);
            } else if (this.filter === 'videos') {
                filtered = filtered.filter(v => !v.is_short);
            }
            if (this.sortBy === 'newest') {
                 // Ensure published_at exists and is valid before sorting
                 filtered.sort((a, b) => {
                     const dateA = a.published_at ? new Date(a.published_at) : 0;
                     const dateB = b.published_at ? new Date(b.published_at) : 0;
                     return dateB - dateA;
                 });
            } else if (this.sortBy === 'views') {
                 // Ensure view_count exists and is numeric
                filtered.sort((a, b) => (b.view_count || 0) - (a.view_count || 0));
            }
            return filtered;
        },

        toggleBulkEditMode() {
            this.bulkEditMode = !this.bulkEditMode;
            if (!this.bulkEditMode) {
                this.selectedVideos = [];
            }
            this.limitMessage = "";
            this.isIndeterminate = false;
            this.calculateRemaining(); // Recalculate remaining on mode toggle
        },


        toggleSelectAll(event) {
            if (!this.bulkEditMode) return;

            const visibleIds = this.filteredAndSortedVideos.map(v => v.id);
            // Non-visible IDs that are currently selected
            const currentlySelectedNotVisibleIds = this.selectedVideos.filter(id => !visibleIds.includes(id));
            // Visible IDs that are currently selected
            const currentlySelectedVisibleIds = visibleIds.filter(id => this.selectedVideos.includes(id));

            if (event.target.checked) {
                // Calculate how many *more* videos can be selected today, considering non-visible selected items
                const canSelectMore = (this.dailyLimit === Infinity) ? Infinity : Math.max(0, this.dailyLimit - this.editsUsedToday - currentlySelectedNotVisibleIds.length);
                // Filter visible IDs that are not already selected, and take up to the limit
                const idsToAdd = visibleIds
                    .filter(id => !this.selectedVideos.includes(id))
                    .slice(0, canSelectMore);

                // Reconstruct selectedVideos: keep non-visible, keep already selected visible, add new ones
                this.selectedVideos = [...currentlySelectedNotVisibleIds, ...currentlySelectedVisibleIds, ...idsToAdd];

                if (idsToAdd.length < (visibleIds.length - currentlySelectedVisibleIds.length)) {
                    // Not all visible items could be added due to limit
                    this.limitMessage = `Selected ${idsToAdd.length} more videos due to daily limit.`;
                    setTimeout(() => this.limitMessage = "", 3000);
                    event.target.checked = false; // Visually uncheck
                    this.isIndeterminate = (this.selectedVideos.length > 0); // Mark as indeterminate
                } else {
                    // All possible visible items were added
                    this.limitMessage = "";
                    this.isIndeterminate = false; // Mark as fully checked (not indeterminate)
                }

            } else {
                // Deselect only the currently visible videos
                this.selectedVideos = currentlySelectedNotVisibleIds;
                this.limitMessage = "";
                this.isIndeterminate = false; // Reset indeterminate state
            }
            this.calculateRemaining(); // Update based on new selection count
            this.updateIndeterminateState(); // Ensure correct final state
        },


        handleCardClick(videoId) {
            if (this.bulkEditMode) {
                const index = this.selectedVideos.indexOf(videoId);

                if (index > -1) {
                     // Deselecting
                     this.selectedVideos.splice(index, 1);
                     this.limitMessage = ""; // Clear message
                } else {
                    // Selecting - check limit first
                    // How many more items can we select today?
                    const canSelectMore = (this.dailyLimit === Infinity) ? 1 : Math.max(0, this.dailyLimit - this.editsUsedToday - this.selectedVideos.length);

                    if (canSelectMore <= 0) {
                         // Cannot select more, show limit message
                         this.calculateRemaining(); // Update remaining count first
                         this.limitMessage = this.getLimitMessage();
                         setTimeout(() => this.limitMessage = "", 3000);
                         return; // Stop selection
                    } else {
                        // Can select, add the video
                        this.selectedVideos.push(videoId);
                        this.limitMessage = ""; // Clear message
                    }
                }
                // Update UI state after selection change
                this.calculateRemainingBasedOnSelection(); // Update for immediate UI feedback if needed
                this.updateIndeterminateState();

            } else {
                // Normal mode: Navigate using the <a> tag's href
                // Ensure the click event on the card doesn't prevent the link's default action unnecessarily
                // The @click handler on the <a> tag takes care of this
            }
        },


        openBulkEditModal() {
            this.bulkEditData = { tags_to_add: '', tags_to_remove: '', description_append: '', privacy_status: '' };
            this.disclaimerChecked = false;
            this.showBulkEditModal = true;
        },

        submitBulkEdit() {
            if (this.selectedVideos.length === 0) {
                 alert('Please select at least one video.');
                return;
            }
             if (!this.disclaimerChecked) {
                 alert('Please read and acknowledge the disclaimer by checking the box before proceeding.');
                 return;
            }
            // Final limit check before showing confirmation
            // How many more *edits* are allowed today?
             const canEditCount = (this.dailyLimit === Infinity) ? Infinity : Math.max(0, this.dailyLimit - this.editsUsedToday);
             if (this.selectedVideos.length > canEditCount) {
                 alert(`You have selected ${this.selectedVideos.length} videos, but you can only edit ${canEditCount} more today based on your plan limit.`);
                 return;
             }

            this.showConfirmModal = true;
        },

         async proceedWithBulkEdit() {
             this.showConfirmModal = false;
            this.isBulkUpdating = true;
            const payload = { video_ids: this.selectedVideos, operations: this.bulkEditData };
            let responseStatus = 0;
            let responseData = null;
            const originalEditsUsed = this.editsUsedToday; // Store before potential update

            try {
                const csrfToken = document.querySelector('input[name="csrf_token"]').value;
                const response = await fetch('/manage/videos/bulk-edit', {
                    method: 'POST',
                     headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify(payload)
                });
                responseStatus = response.status;
                responseData = await response.json();

                if (!response.ok) {
                    throw new Error(responseData.error || `Server error: ${response.status}`);
                }

                // Success - Show message from backend
                alert(responseData.message);

                // Reload the page to show updated counts and potentially disable selection
                window.location.reload();

            } catch (error) {
                 // Handle specific 429 error
                 if (responseStatus === 429) {
                     alert('Error: ' + (responseData.error || 'Daily bulk edit limit exceeded.'));
                     // Keep modal open, reset disclaimer check
                     this.disclaimerChecked = false;
                 } else {
                     // Handle other errors
                     alert('Error: ' + error.message);
                      // Close modal on other errors
                      this.showBulkEditModal = false;
                 }
            } finally {
                 // Stop loading indicator only if the operation is definitively finished
                 // Keep loading if reload is initiated by success
                 if (!(responseStatus >= 200 && responseStatus < 300)) {
                    this.isBulkUpdating = false;
                 }
                 // If 429, keep modal open, stop loading
                 if (responseStatus === 429) {
                     this.isBulkUpdating = false;
                 }
            }
        },

        formatRelativeTime(isoDate) {
             if (!isoDate) return '';
            try {
                const dt = new Date(isoDate);
                const now = new Date();
                // Basic timezone handling assumes server provides UTC ISO strings
                const diffMs = now.getTime() - dt.getTime();
                const diffSeconds = Math.round(diffMs / 1000);

                if (diffSeconds < 60) return 'just now';
                const minutes = Math.floor(diffSeconds / 60);
                if (minutes < 60) return `${minutes}m ago`;
                const hours = Math.floor(minutes / 60);
                if (hours < 24) return `${hours}h ago`;
                const days = Math.floor(hours / 24);
                // Show date if older than 7 days
                if (days < 7) return `${days}d ago`;
                return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }); // e.g., Oct 24
            } catch (e) {
                console.error("Error formatting date:", isoDate, e);
                return 'Invalid Date'; // Fallback for invalid date strings
            }
        }
    }
}

// Ensure Alpine is initialized after the PAGE_DATA script tag in HTML
document.addEventListener('alpine:init', () => {
    Alpine.data('videoManager', videoManager);
});