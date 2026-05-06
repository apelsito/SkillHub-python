import { describe, expect, it } from 'vitest'
import en from './locales/en.json'

describe('skill detail lifecycle locale', () => {
  it('defines the unarchive label', () => {
    expect(en.skillDetail.unarchiveSkill).toBe('Restore Skill')
  })
})
