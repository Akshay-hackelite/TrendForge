import SheetCommentCell from './SheetCommentCell'
import { stagePillClass, typePillClass } from './sheetUtils'
import { formatChipRange, weekRanges } from '../tracker/trackerUtils'

function groupByWeek(rows = []) {
  const map = new Map()
  for (const row of rows) {
    if (!map.has(row.week)) map.set(row.week, [])
    map.get(row.week).push(row)
  }
  return [...map.entries()].map(([week, weekRows]) => ({ week, rows: weekRows }))
}

export default function WeeklySheetTable({ rows = [], comments = {}, year, month, onCommentSave }) {
  const weekGroups = groupByWeek(rows)
  const ranges = weekRanges(year, month)

  if (!weekGroups.length) {
    return <p className="text-muted sheet-empty">No tracker cards for this month yet.</p>
  }

  return (
    <div className="sheet-week-stack">
      {weekGroups.map(({ week, rows: weekRows }) => {
        const range = ranges.find((row) => row.week === week)
        return (
        <section key={week} className="sheet-week-block">
          <header className="sheet-week-block-head">
            <div>
              <strong>Week {week}</strong>
              {range ? <span>{formatChipRange(year, month, range.start, range.end)}</span> : null}
            </div>
            <em>{weekRows.length} card{weekRows.length === 1 ? '' : 's'}</em>
          </header>
          <div className="sheet-table-wrap sheet-table-wrap-nested">
            <table className="sheet-table">
              <thead>
                <tr>
                  <th>Content type</th>
                  <th>Stage</th>
                  <th>Relevant link</th>
                  <th>Comments</th>
                </tr>
              </thead>
              <tbody>
                {weekRows.map((row) => (
                  <tr key={`${row.week}-${row.card_id}`}>
                    <td>
                      <span className={`tracker-pill ${typePillClass(row.content_type)}`}>
                        {row.content_type_label}
                      </span>
                    </td>
                    <td>
                      <span className={`sheet-pill ${stagePillClass(row.stage)}`}>
                        {row.stage_label}
                      </span>
                    </td>
                    <td className="sheet-links-cell">
                      {(row.links || []).length ? (
                        <div className="sheet-links">
                          {row.links.map((url) => (
                            <a key={url} href={url} target="_blank" rel="noreferrer">{url}</a>
                          ))}
                        </div>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td>
                      <SheetCommentCell
                        value={comments[row.row_key] || ''}
                        onSave={(comment) => onCommentSave(row, comment)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        )
      })}
    </div>
  )
}
