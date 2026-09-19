import { useCallback, useEffect, useRef, useState } from 'react'
import TrackerCard from './TrackerCard'
import {
  cardsSummary,
  displayLanguages,
  emptyCard,
  seedDestinations,
  serializableCard,
  startCard,
} from './trackerUtils'
import api from '../../api'
import { useAuth } from '../../context/AuthContext'
import { useUI } from '../../context/UIContext'

export default function TrackerWeekBoard({ clientId, year, month, week, onSummaryChange }) {
  const { token } = useAuth()
  const { toast } = useUI()
  const [cards, setCards] = useState([])
  const [languages, setLanguages] = useState([])
  const [loading, setLoading] = useState(true)
  const [dragId, setDragId] = useState(null)
  const [dropTargetId, setDropTargetId] = useState(null)
  const [scriptedItems, setScriptedItems] = useState([])
  const [scriptBusyId, setScriptBusyId] = useState(null)
  const [channels, setChannels] = useState([])
  const saveTimer = useRef(null)
  const skipNextSave = useRef(true)
  const loadedKey = useRef('')
  const onSummaryChangeRef = useRef(onSummaryChange)
  onSummaryChangeRef.current = onSummaryChange

  const loadWeek = useCallback(async (nextClientId, nextYear, nextMonth, nextWeek) => {
    if (!token || !nextClientId) return
    setLoading(true)
    try {
      const result = await api.getWeeklyTracker(token, nextClientId, nextYear, nextMonth, nextWeek)
      loadedKey.current = `${nextClientId}-${nextYear}-${nextMonth}-${nextWeek}`
      skipNextSave.current = true
      const langs = displayLanguages(result.languages || [])
      const nextCards = (result.tracker?.cards || []).map((card) => {
        let next = card
        if (next.started && !(next.destinations || []).length) {
          next = { ...next, destinations: seedDestinations(next, langs) }
        }
        return next
      })
      setCards(nextCards)
      setLanguages(langs)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [token, toast])

  const loadScripts = useCallback(async (nextClientId) => {
    if (!token || !nextClientId) return
    try {
      const data = await api.getContentPlan(token, nextClientId)
      setScriptedItems((data.suggestions?.items || []).filter((item) => (item.script || '').trim()))
    } catch (err) {
      toast(err.message, 'error')
    }
  }, [token, toast])

  const loadChannels = useCallback(async (nextClientId) => {
    if (!token || !nextClientId) return
    try {
      const data = await api.listChannels(token, nextClientId)
      setChannels(data.channels || [])
    } catch (err) {
      toast(err.message, 'error')
    }
  }, [token, toast])

  useEffect(() => {
    loadWeek(clientId, year, month, week)
  }, [clientId, year, month, week, loadWeek])

  useEffect(() => {
    loadScripts(clientId)
    loadChannels(clientId)
  }, [clientId, loadScripts, loadChannels])

  const persist = useCallback((nextCards) => {
    if (!token || !clientId) return
    const key = `${clientId}-${year}-${month}-${week}`
    if (loadedKey.current !== key) return
    clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(async () => {
      if (loadedKey.current !== key) return
      try {
        await api.saveWeeklyTracker(
          token,
          clientId,
          year,
          month,
          week,
          nextCards.map(serializableCard),
        )
      } catch (err) {
        toast(err.message, 'error')
      }
    }, 400)
  }, [token, clientId, year, month, week, toast])

  useEffect(() => {
    if (skipNextSave.current) {
      skipNextSave.current = false
      return
    }
    persist(cards)
  }, [cards, persist])

  useEffect(() => {
    if (loading || !onSummaryChangeRef.current) return
    const summary = cardsSummary(cards)
    onSummaryChangeRef.current(clientId, week, {
      week,
      out: summary.out,
      total: summary.total,
      to_start: summary.toStart,
    })
  }, [cards, week, loading, clientId])

  useEffect(() => () => clearTimeout(saveTimer.current), [])

  function applyWeekUpdate(result) {
    skipNextSave.current = true
    setCards(result.tracker?.cards || [])
    if (result.languages) setLanguages(result.languages)
  }

  function patchCard(nextCard) {
    setCards((prev) => prev.map((card) => (card.id === nextCard.id ? nextCard : card)))
  }

  function addCard(type, afterId = null) {
    setCards((prev) => {
      const extra = emptyCard(type, prev.length, false)
      if (!afterId) return [...prev, extra]
      const idx = prev.findIndex((card) => card.id === afterId)
      const next = [...prev]
      next.splice(idx + 1, 0, extra)
      return next.map((card, index) => ({ ...card, sort_order: index }))
    })
  }

  function startAllDefaults() {
    const langs = displayLanguages(languages)
    setCards((prev) => prev.map((card) => (
      card.is_default && !card.started ? startCard(card, langs) : card
    )))
  }

  function removeCard(cardId) {
    const next = cards.filter((card) => card.id !== cardId).map((card, index) => ({ ...card, sort_order: index }))
    skipNextSave.current = true
    setCards(next)
    if (token && clientId) {
      api.saveWeeklyTracker(
        token,
        clientId,
        year,
        month,
        week,
        next.map(serializableCard),
      ).catch((err) => toast(err.message, 'error'))
    }
    toast('Card removed', 'success')
  }

  function clearDrag() {
    setDragId(null)
    setDropTargetId(null)
  }

  function handleDrop(targetId) {
    if (!dragId || dragId === targetId) {
      clearDrag()
      return
    }
    setCards((prev) => {
      const from = prev.findIndex((card) => card.id === dragId)
      const to = prev.findIndex((card) => card.id === targetId)
      if (from < 0 || to < 0) return prev
      const next = [...prev]
      const [moved] = next.splice(from, 1)
      next.splice(to, 0, moved)
      return next.map((card, index) => ({ ...card, sort_order: index }))
    })
    clearDrag()
  }

  const weekContext = {
    token,
    clientId,
    year,
    month,
    week,
    toast,
    channels,
    onWeekUpdate: applyWeekUpdate,
    reloadWeek: async () => {
      if (!token || !clientId) return null
      const result = await api.getWeeklyTracker(token, clientId, year, month, week)
      applyWeekUpdate(result)
      return result
    },
  }

  async function handlePickScript(card, item) {
    if (!token || !clientId || !item?.id) return
    setScriptBusyId(card.id)
    try {
      const result = await api.attachTrackerScript(token, clientId, {
        itemId: item.id,
        year,
        month,
        week,
        cardId: card.id,
      })
      applyWeekUpdate(result)
      if (result.status === 'already') {
        toast('Already on this card', 'info')
      } else if (card.content_plan_item_id && card.content_plan_item_id !== item.id) {
        toast('Script changed', 'success')
      } else {
        toast('Script added to this card', 'success')
      }
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setScriptBusyId(null)
    }
  }

  async function handleSaveScriptText(card, text) {
    if (!token || !clientId) return
    setScriptBusyId(card.id)
    try {
      if (card.content_plan_item_id) {
        await api.updateContentScript(token, clientId, {
          itemId: card.content_plan_item_id,
          script: text,
        })
        skipNextSave.current = true
        setCards((prev) => prev.map((row) => {
          if (row.content_plan_item_id !== card.content_plan_item_id) return row
          return {
            ...row,
            assets: { ...(row.assets || {}), script_text: text, script_url: '' },
          }
        }))
        await loadScripts(clientId)
        toast('Script updated in tracker and content plan', 'success')
      } else {
        patchCard({
          ...card,
          assets: { ...(card.assets || {}), script_text: text, script_url: '' },
        })
        toast('Script saved on this card', 'success')
      }
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setScriptBusyId(null)
    }
  }

  if (loading) {
    return <p className="text-muted" style={{ padding: '16px 0' }}>Loading week…</p>
  }

  return (
    <div className="tracker-week-board">
      <div className="tracker-card-stack">
        {cards.map((card) => (
          <TrackerCard
            key={card.id}
            card={card}
            languages={displayLanguages(languages)}
            weekContext={weekContext}
            scriptedItems={scriptedItems.filter((item) => (
              card.type === 'short' ? item.format === 'Short' : item.format !== 'Short'
            ))}
            scriptBusy={scriptBusyId === card.id}
            onPickScript={(item) => handlePickScript(card, item)}
            onSaveScriptText={(text) => handleSaveScriptText(card, text)}
            onChange={patchCard}
            onStart={() => patchCard(startCard(card, displayLanguages(languages)))}
            onAddSameType={() => addCard(card.type, card.id)}
            onRemove={() => removeCard(card.id)}
            isDragging={dragId === card.id}
            isDropTarget={Boolean(dragId && dropTargetId === card.id && dragId !== card.id)}
            onDragStart={() => setDragId(card.id)}
            onDragEnd={clearDrag}
            onDragOver={(event) => {
              event.preventDefault()
              if (dropTargetId !== card.id) setDropTargetId(card.id)
            }}
            onDrop={() => handleDrop(card.id)}
          />
        ))}
      </div>
      <div className="tracker-bubbles">
        <button type="button" className="btn btn-primary" onClick={startAllDefaults}>Start all 4</button>
        <button type="button" className="btn btn-secondary" onClick={() => addCard('long_video')}>+ Long video</button>
        <button type="button" className="btn btn-secondary" onClick={() => addCard('short')}>+ Short</button>
        <button type="button" className="btn btn-secondary" onClick={() => addCard('static_post')}>+ Static post</button>
        <button type="button" className="btn btn-secondary" onClick={() => addCard('blog')}>+ Blog</button>
      </div>
    </div>
  )
}
