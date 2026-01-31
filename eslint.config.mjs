import globals from 'globals';

export default [
  {
    files: ['src/vibes/static/js/**/*.js'],
    ignores: [
      'src/vibes/static/js/marked.min.js',
      'src/vibes/static/js/vendor/**',
    ],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        ...globals.browser,
      },
    },
    rules: {
      'no-unused-vars': 'off',
    },
  },
];
