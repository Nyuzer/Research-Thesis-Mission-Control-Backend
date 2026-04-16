import * as React from "react"
import { format } from "date-fns"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"
import { CalendarClock } from "lucide-react"

interface DateTimePickerProps {
  value: string            // ISO string or "" (e.g. "2026-04-16T14:30")
  onChange: (v: string) => void
  className?: string
  placeholder?: string
}

export function DateTimePicker({ value, onChange, className, placeholder = "Pick date & time" }: DateTimePickerProps) {
  const parsed = value ? new Date(value) : undefined
  const isValid = parsed && !isNaN(parsed.getTime())

  const hours = isValid ? String(parsed.getHours()).padStart(2, "0") : "12"
  const minutes = isValid ? String(parsed.getMinutes()).padStart(2, "0") : "00"

  const setDate = (d: Date | undefined) => {
    if (!d) return
    const h = isValid ? parsed.getHours() : 12
    const m = isValid ? parsed.getMinutes() : 0
    d.setHours(h, m, 0, 0)
    onChange(toLocalISO(d))
  }

  const setTime = (h: string, m: string) => {
    const d = isValid ? new Date(parsed) : new Date()
    d.setHours(parseInt(h) || 0, parseInt(m) || 0, 0, 0)
    onChange(toLocalISO(d))
  }

  return (
    <Popover>
      <PopoverTrigger
        className={cn(
          "inline-flex items-center gap-2 h-8 w-full text-xs font-normal px-3 border rounded-md bg-background shadow-xs hover:bg-accent hover:text-accent-foreground dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
          !isValid && "text-muted-foreground",
          className,
        )}
      >
        <CalendarClock className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        {isValid ? format(parsed, "dd.MM.yyyy  HH:mm") : placeholder}
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="single"
          selected={isValid ? parsed : undefined}
          onSelect={setDate}
        />
        <div className="flex items-center gap-1.5 px-3 pb-3 border-t border-border pt-2">
          <span className="text-xs text-muted-foreground">Time:</span>
          <input
            type="number"
            min={0}
            max={23}
            value={hours}
            onChange={(e) => setTime(e.target.value, minutes)}
            className="w-10 h-7 text-center text-xs bg-background border border-input rounded-md [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
          />
          <span className="text-xs text-muted-foreground">:</span>
          <input
            type="number"
            min={0}
            max={59}
            value={minutes}
            onChange={(e) => setTime(hours, e.target.value)}
            className="w-10 h-7 text-center text-xs bg-background border border-input rounded-md [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
          />
        </div>
      </PopoverContent>
    </Popover>
  )
}

function toLocalISO(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
