import { describe, expect, it } from 'vitest'
import en from './locales/en.json'

describe('landing quick start locale', () => {
  it('uses the English agent setup prompt', () => {
    expect(en.landing.quickStart.agent.command).toBe('Read https://www.example.com/registry/skill.md and follow the instructions to setup SkillHub Skills Registry')
  })

  it('provides a command template with url placeholder for dynamic rendering', () => {
    expect(en.landing.quickStart.agent.commandTemplate).toBe('Read {{url}} and follow the instructions to setup SkillHub Skills Registry')
  })
})
