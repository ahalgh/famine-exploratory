// Every data file is resolved against the app's base path, so the site works at a domain root
// (`/`) or under a sub-path such as GitHub Pages' `/famine-exploratory/` (set with BASE_PATH at build).
export const asset = (path) => new URL(`${import.meta.env.BASE_URL}${path.replace(/^\//, '')}`, location.href).href;
