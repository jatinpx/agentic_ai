import * as React from "react"

import { cn } from "../utils"

const ScrollArea = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "scroll-area overflow-y-auto scrollbar-thin scrollbar-thumb-rounded scrollbar-thumb-gray-300 scrollbar-track-gray-100",
        className
      )}
      {...props}
    />
  )
)
ScrollArea.displayName = "ScrollArea"

export { ScrollArea }
