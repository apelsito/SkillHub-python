import { describe, expect, it } from 'vitest'
import { resolveReviewActionErrorDescription } from './review-error'

describe('resolveReviewActionErrorDescription', () => {
  it('returns the error message when present', () => {
    expect(resolveReviewActionErrorDescription(new Error('Review rule validation failed'))).toBe('Review rule validation failed')
  })

  it('returns undefined for blank or non-error values', () => {
    expect(resolveReviewActionErrorDescription(new Error('   '))).toBeUndefined()
    expect(resolveReviewActionErrorDescription('Review failed')).toBeUndefined()
  })
})
