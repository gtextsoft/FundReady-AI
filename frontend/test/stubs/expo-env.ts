/**
 * `babel-preset-expo` rewrites `process.env` reads into imports from
 * `expo/virtual/env`, which ships as untransformed ESM inside `node_modules`.
 * This is the same module, in a form Jest can load.
 */
export const env = process.env;
