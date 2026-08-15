import { describe, expect, it } from 'vitest'
import { folderLabel } from './WorkspaceFooter.tsx'

describe('folderLabel', () => {
  it('returns empty copy when path is missing', () => {
    expect(folderLabel(null, null)).toBe('Папка не открыта')
    expect(folderLabel(null, 'Docs')).toBe('Папка не открыта')
  })

  it('prefers a non-empty display name', () => {
    expect(folderLabel('/Users/me/Docs', 'Docs')).toBe('Docs')
  })

  it('falls back to the last path segment', () => {
    expect(folderLabel('/Users/me/Docs', null)).toBe('Docs')
    expect(folderLabel('/Users/me/Docs/', '   ')).toBe('Docs')
  })

  it('returns the path itself when the last segment is empty', () => {
    expect(folderLabel('/', null)).toBe('/')
  })
})
