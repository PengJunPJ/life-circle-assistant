import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import pluginVue from 'eslint-plugin-vue'

export default [
  { ignores: ['dist/**', 'coverage/**', 'node_modules/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/essential'],
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
        extraFileExtensions: ['.vue'],
      },
    },
  },
  {
    files: ['**/*.ts', '**/*.vue'],
    rules: {
      // 未定义名称由 vue-tsc 的类型检查负责，ESLint 不再重复报浏览器/DOM 全局
      'no-undef': 'off',
      // 报告契约与地图返回结构为动态字典，any 在当前阶段是显式取舍而非疏漏
      '@typescript-eslint/no-explicit-any': 'off',
      // 组件名沿用业务语义（如 ReportPanel），不强制多词命名
      'vue/multi-word-component-names': 'off',
    },
  },
  {
    files: ['**/*.test.ts'],
    rules: {
      // 测试夹具允许未使用的占位参数与宽松断言
      '@typescript-eslint/no-unused-vars': 'off',
    },
  },
]
