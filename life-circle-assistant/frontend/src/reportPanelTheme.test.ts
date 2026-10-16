import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const styles = readFileSync(new URL('./styles.css', import.meta.url), 'utf8')

describe('社区体检报告空状态深色主题', () => {
  it('报告操作区在无报告时仍保持可读层级，并区分禁用按钮', () => {
    expect(styles).toMatch(/html\[data-theme="dark"\] \.report-actions button \{[^}]*color:\s*#cfe7e1;/s)
    expect(styles).toMatch(/html\[data-theme="dark"\] \.report-actions button:disabled \{[^}]*opacity:\s*\.68;/s)
    expect(styles).toMatch(/html\[data-theme="dark"\] \.report-actions button\[aria-pressed="true"\]/)
  })

  it('空报告提示和历史入口在深色主题下具有明确对比度', () => {
    expect(styles).toMatch(/html\[data-theme="dark"\] \.empty-report \{[^}]*color:\s*#9db8b8;/s)
    expect(styles).toMatch(/html\[data-theme="dark"\] \.empty-report strong \{[^}]*color:\s*#eaf6f3;/s)
    expect(styles).toMatch(/html\[data-theme="dark"\] \.empty-report span \{[^}]*color:\s*#9db8b8;/s)
    expect(styles).toMatch(/html\[data-theme="dark"\] \.empty-report button \{[^}]*border:/s)
  })
})
