import js from '@eslint/js';
import globals from 'globals';

export default [
  js.configs.recommended,
  {
    files: ['static/js/**/*.js', 'tests/**/*.mjs', 'scripts/**/*.mjs'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    rules: {
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      'no-useless-escape': 'warn',
      'no-console': 'off',
    },
  },
  {
    ignores: ['static/dist/**', 'static/js/vendor/**', 'static/js/marked.min.js', 'node_modules/**'],
  },
];
