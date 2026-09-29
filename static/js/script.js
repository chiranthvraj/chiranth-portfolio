const menuButton = document.querySelector(".menu-toggle");
const navigation = document.querySelector("#nav-links");

if (menuButton && navigation) {
  menuButton.addEventListener("click", () => {
    const isOpen = menuButton.getAttribute("aria-expanded") === "true";
    menuButton.setAttribute("aria-expanded", String(!isOpen));
    navigation.classList.toggle("is-open", !isOpen);
  });

  navigation.addEventListener("click", (event) => {
    if (event.target instanceof Element && event.target.closest("a")) {
      menuButton.setAttribute("aria-expanded", "false");
      navigation.classList.remove("is-open");
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && menuButton.getAttribute("aria-expanded") === "true") {
      menuButton.setAttribute("aria-expanded", "false");
      navigation.classList.remove("is-open");
      menuButton.focus();
    }
  });
}

const contactForm = document.querySelector("[data-contact-form]");
const messageField = document.querySelector("#message");
const characterCount = document.querySelector("#message-count");

if (contactForm && messageField instanceof HTMLTextAreaElement && characterCount) {
  const updateCharacterCount = () => {
    characterCount.textContent = `${messageField.value.length} / ${messageField.maxLength} characters`;
  };

  messageField.addEventListener("input", updateCharacterCount);
  contactForm.addEventListener("reset", () => {
    window.requestAnimationFrame(updateCharacterCount);
  });
  updateCharacterCount();
}
