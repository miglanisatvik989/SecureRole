const toggle = document.querySelector(".password-toggle");

if (toggle) {
    const password = document.getElementById(toggle.getAttribute("aria-controls"));
    toggle.hidden = false;

    toggle.addEventListener("click", () => {
        const show = password.type === "password";
        password.type = show ? "text" : "password";
        toggle.setAttribute("aria-label", show ? "Hide password" : "Show password");
        toggle.classList.toggle("is-visible", show);
    });
}

for (const trigger of document.querySelectorAll("[data-confirm]")) {
    const dialog = document.getElementById(trigger.dataset.confirm);
    if (!dialog || typeof dialog.showModal !== "function") continue;
    trigger.addEventListener("click", (event) => {
        event.preventDefault();
        dialog.showModal();
    });
}

for (const form of document.querySelectorAll("[data-submission-feedback]")) {
    const status = form.querySelector(".submission-status");
    form.addEventListener("submit", (event) => {
        if (form.dataset.pending) {
            event.preventDefault();
            return;
        }
        form.dataset.pending = "true";
        event.submitter?.setAttribute("aria-disabled", "true");
        status.textContent = "Submitting…";
    });
    window.addEventListener("pageshow", () => {
        delete form.dataset.pending;
        for (const control of form.querySelectorAll('[aria-disabled="true"]')) {
            control.removeAttribute("aria-disabled");
        }
        status.textContent = "";
    });
}
