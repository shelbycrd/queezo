export const buttonFeedback = {
  mounted(element) {
    const controller = new AbortController();
    let timer, pressed;
    element.addEventListener('click', event => {
      const button = event.target.closest('button,.button,.photo-picker');
      if (!button || button.disabled) return;
      clearTimeout(timer);
      pressed?.classList.remove('is-pressed');
      pressed = button;
      button.classList.add('is-pressed');
      timer = setTimeout(() => button.classList.remove('is-pressed'), 130);
    }, {signal:controller.signal, capture:true});
    element.feedbackCleanup = () => { controller.abort(); clearTimeout(timer); pressed?.classList.remove('is-pressed'); };
  },
  unmounted(element) { element.feedbackCleanup?.(); },
};
