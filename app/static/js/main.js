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
