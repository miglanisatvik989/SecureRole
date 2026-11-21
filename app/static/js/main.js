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

const menu = document.querySelector("[data-nav-toggle]");

if (menu) {
    const sidebar = menu.closest(".sidebar");
    const content = document.getElementById(menu.getAttribute("aria-controls"));
    const compact = window.matchMedia("(max-width: 768px)");

    function setExpanded(expanded) {
        if (!expanded && content.contains(document.activeElement)) menu.focus();
        content.hidden = !expanded;
        menu.setAttribute("aria-expanded", String(expanded));
    }

    function syncNavigation() {
        if (compact.matches) {
            menu.hidden = false;
            setExpanded(false);
        } else {
            if (document.activeElement === menu) sidebar.querySelector(".brand").focus();
            menu.hidden = true;
            setExpanded(true);
        }
    }

    menu.addEventListener("click", () => setExpanded(content.hidden));
    sidebar.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && compact.matches && !content.hidden) {
            event.preventDefault();
            setExpanded(false);
            menu.focus();
        }
    });
    compact.addEventListener("change", syncNavigation);
    syncNavigation();
}
