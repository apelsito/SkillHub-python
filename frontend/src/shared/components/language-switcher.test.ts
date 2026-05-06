import { describe, expect, it } from 'vitest'
import * as mod from './language-switcher'

/**
 * LanguageSwitcher is intentionally English-only while keeping a stable export
 * for the app shell.
 */
describe('language-switcher module exports', () => {
  it('exports the LanguageSwitcher component', () => {
    expect(mod.LanguageSwitcher).toBeTypeOf('function')
  })
})
