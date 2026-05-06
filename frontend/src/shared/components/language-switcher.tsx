import { Globe } from 'lucide-react'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/utils'

interface LanguageSwitcherProps {
  className?: string
}

export function LanguageSwitcher({ className }: LanguageSwitcherProps) {
  return (
    <Button
      variant="ghost"
      size="sm"
      className={cn('cursor-default gap-2 text-muted-foreground', className)}
      aria-label="Current language: English"
      title="English"
    >
      <Globe className="h-4 w-4" />
      <span className="text-sm text-inherit">English</span>
    </Button>
  )
}
