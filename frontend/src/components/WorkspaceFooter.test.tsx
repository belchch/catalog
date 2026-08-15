import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { WorkspaceFooter } from './WorkspaceFooter.tsx'

afterEach(cleanup)

describe('WorkspaceFooter', () => {
  it('shows muted empty copy and no rescan without a workspace', () => {
    const onOpenPicker = vi.fn()
    render(
      <WorkspaceFooter
        path={null}
        displayName={null}
        rescanning={false}
        onOpenPicker={onOpenPicker}
        onRescan={() => {}}
      />,
    )
    const picker = screen.getByRole('button', { name: 'Выбрать воркспейс: Папка не открыта' })
    expect(picker.getAttribute('title')).toBeNull()
    expect(picker.textContent).not.toContain('⌄')
    expect(screen.queryByRole('button', { name: 'Пересканировать папку' })).toBeNull()
    picker.click()
    expect(onOpenPicker).toHaveBeenCalledTimes(1)
  })

  it('shows folderLabel, path title, and a sibling rescan button', () => {
    const onOpenPicker = vi.fn()
    const onRescan = vi.fn()
    render(
      <WorkspaceFooter
        path="/Users/me/Docs"
        displayName="Docs"
        rescanning={false}
        onOpenPicker={onOpenPicker}
        onRescan={onRescan}
      />,
    )
    const picker = screen.getByRole('button', { name: 'Выбрать воркспейс: Docs' })
    expect(picker.getAttribute('title')).toBe('/Users/me/Docs')
    expect(picker.textContent).not.toContain('⌄')
    const rescan = screen.getByRole('button', { name: 'Пересканировать папку' })
    expect(rescan.parentElement?.contains(picker)).toBe(true)
    expect(picker.contains(rescan)).toBe(false)
    rescan.click()
    expect(onRescan).toHaveBeenCalledTimes(1)
    expect(onOpenPicker).not.toHaveBeenCalled()
  })

  it('disables rescan and marks it busy while rescanning', () => {
    render(
      <WorkspaceFooter
        path="/Users/me/Docs"
        displayName="Docs"
        rescanning={true}
        onOpenPicker={() => {}}
        onRescan={() => {}}
      />,
    )
    const rescan = screen.getByRole('button', { name: 'Пересканировать папку' })
    expect(rescan.hasAttribute('disabled')).toBe(true)
    expect(rescan.getAttribute('aria-busy')).toBe('true')
  })
})
