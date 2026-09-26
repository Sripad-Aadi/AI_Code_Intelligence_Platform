import { useEffect } from 'react'

/** Set the browser-tab title for a page and restore it on unmount.
 *
 * Page-specific tab titles avoid duplicating the "AI Software Intelligence"
 * brand that already sits in the navbar / login card.
 */
export function usePageTitle(title: string): void {
  useEffect(() => {
    const previous = document.title
    document.title = title
    return () => {
      document.title = previous
    }
  }, [title])
}