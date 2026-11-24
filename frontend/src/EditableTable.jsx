function Cell({ col, row, set }) {
  const value = row[col.key];
  const disabled = col.enabled ? !col.enabled(row) : false;
  if (col.type === "select")
    return (
      <select value={value ?? ""} disabled={disabled} onChange={(e) => set(e.target.value)}>
        <option value=""></option>
        {(col.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    );
  if (col.type === "multi")
    return (
      <select multiple size={3} value={value || []} disabled={disabled}
              onChange={(e) => set([...e.target.selectedOptions].map((o) => o.value))}>
        {(col.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    );
  if (col.type === "text")
    return <input value={value ?? ""} disabled={disabled} onChange={(e) => set(e.target.value)} />;
  return (
    <input type="number" step="any" value={value ?? ""} disabled={disabled}
           onChange={(e) => set(e.target.value === "" ? "" : Number(e.target.value))} />
  );
}

export default function EditableTable({ columns, rows, onChange, newRow, addLabel = "Добавить" }) {
  const setCell = (i, key, v) => onChange(rows.map((r, j) => (j === i ? { ...r, [key]: v } : r)));
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{columns.map((c) => <th key={c.key}>{c.label}</th>)}<th /></tr></thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => <td key={c.key}><Cell col={c} row={row} set={(v) => setCell(i, c.key, v)} /></td>)}
              <td><button className="danger" onClick={() => onChange(rows.filter((_, j) => j !== i))}>✕</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <button onClick={() => onChange([...rows, newRow(rows)])}>{addLabel}</button>
    </div>
  );
}
