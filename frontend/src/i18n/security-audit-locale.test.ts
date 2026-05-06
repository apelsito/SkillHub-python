import { describe, expect, it } from 'vitest'
import en from './locales/en.json'

describe('security audit locale', () => {
  it('defines the scanning label', () => {
    expect(en.securityAudit.statusScanning).toBe('Scanning')
  })

  it('uses the updated blocked wording', () => {
    expect(en.securityAudit.verdict.BLOCKED).toBe('High Risk')
  })
})
