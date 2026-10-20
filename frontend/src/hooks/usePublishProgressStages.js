import { useEffect, useRef, useState } from 'react'

export function usePublishProgressStages() {
  const [stage, setStage] = useState('Starting publish…')
  const [elapsed, setElapsed] = useState(0)
  const [busy, setBusy] = useState(false)
  const started = useRef(0)

  useEffect(() => {
    if (!busy) return undefined
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - started.current) / 1000))
    }, 1000)
    return () => clearInterval(id)
  }, [busy])

  function start() {
    started.current = Date.now()
    setElapsed(0)
    setStage('Starting publish…')
    setBusy(true)
  }

  function stop() {
    setBusy(false)
  }

  return { stage, elapsed, busy, start, stop, setStage }
}
