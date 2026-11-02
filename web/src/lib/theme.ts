export const THEME_KEY = "theme";

/** Runs in <head> before the page paints, so a saved light theme doesn't flash dark first. */
export const THEME_SCRIPT = `try{if(localStorage.getItem("${THEME_KEY}")==="light")document.documentElement.dataset.theme="light"}catch(e){}`;
