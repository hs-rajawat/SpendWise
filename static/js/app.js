/* SpendWise — small progressive enhancements only. */

(function () {
  "use strict";

  const body = document.body;

  /* ---------- Sidebar navigation ---------- */
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebar-overlay");
  const navToggle = document.getElementById("nav-toggle");

  function openNav() {
    if (!sidebar || !overlay || !navToggle) return;
    sidebar.classList.add("is-open");
    overlay.classList.add("is-visible");
    body.classList.add("nav-open");
    navToggle.setAttribute("aria-expanded", "true");
    navToggle.setAttribute("aria-label", "Close navigation");
  }

  function closeNav() {
    if (!sidebar || !overlay || !navToggle) return;
    sidebar.classList.remove("is-open");
    overlay.classList.remove("is-visible");
    body.classList.remove("nav-open");
    navToggle.setAttribute("aria-expanded", "false");
    navToggle.setAttribute("aria-label", "Open navigation");
  }

  if (navToggle) {
    navToggle.addEventListener("click", function () {
      if (sidebar.classList.contains("is-open")) closeNav();
      else openNav();
    });
  }
  if (overlay) overlay.addEventListener("click", closeNav);
  window.addEventListener("resize", function () {
    if (window.innerWidth > 1120) closeNav();
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeNav();
  });

  /* ---------- Delete confirmation ---------- */
  const dialog = document.getElementById("confirm-dialog");
  const confirmMessage = document.getElementById("confirm-message");
  const confirmButton = dialog ? dialog.querySelector("[data-modal-confirm]") : null;
  const cancelButton = dialog ? dialog.querySelector("[data-modal-cancel]") : null;
  let pendingForm = null;

  if (dialog && confirmButton && typeof dialog.showModal === "function") {
    document.addEventListener("submit", function (event) {
      const form = event.target.closest("form[data-confirm]");
      if (!form) return;
      event.preventDefault();
      pendingForm = form;
      if (confirmMessage) {
        confirmMessage.textContent =
          form.getAttribute("data-confirm") || "This record will be permanently removed.";
      }
      dialog.showModal();
      body.classList.add("modal-open");
    });

    confirmButton.addEventListener("click", function () {
      if (!pendingForm) return;
      const form = pendingForm;
      pendingForm = null;
      dialog.close();
      form.submit();
    });

    if (cancelButton) {
      cancelButton.addEventListener("click", function () {
        pendingForm = null;
        dialog.close();
      });
    }

    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) {
        pendingForm = null;
        dialog.close();
      }
    });

    dialog.addEventListener("close", function () {
      body.classList.remove("modal-open");
    });
  } else {
    document.addEventListener("submit", function (event) {
      const form = event.target.closest("form[data-confirm]");
      if (!form) return;
      if (!window.confirm(form.getAttribute("data-confirm") || "Delete this record?")) {
        event.preventDefault();
      }
    });
  }

  /* ---------- Flash toasts ---------- */
  document.querySelectorAll(".toast").forEach(function (toast, index) {
    let dismissed = false;

    function dismiss() {
      if (dismissed) return;
      dismissed = true;
      toast.classList.add("is-leaving");
      window.setTimeout(function () {
        toast.remove();
      }, 220);
    }

    const close = toast.querySelector(".toast__close");
    if (close) close.addEventListener("click", dismiss);
    window.setTimeout(dismiss, 5000 + index * 200);
  });

  /* ---------- Description character counter ---------- */
  document.querySelectorAll("[data-char-count]").forEach(function (counter) {
    const input = counter.parentElement
      ? counter.parentElement.querySelector("input")
      : null;
    if (!input) return;

    function update() {
      counter.textContent = input.value.length + "/160";
    }

    input.addEventListener("input", update);
    update();
  });

  /* ---------- Auto-submit the analytics month picker ---------- */
  document.querySelectorAll("[data-auto-submit]").forEach(function (input) {
    input.addEventListener("change", function () {
      if (input.form && typeof input.form.requestSubmit === "function") {
        input.form.requestSubmit();
      }
    });
  });
})();
