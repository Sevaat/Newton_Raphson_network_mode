import { useCallback, useEffect, useRef, useState } from "react";
import { api, exportCase } from "./api";
import EditableTable from "./EditableTable";

const KIND_SECTION = { line: "LINES", t2: "TRANSFORMERS2", t3: "TRANSFORMERS3" };
const BRANCH_BASE = ["branch_name", "node_1", "node_2", "r_1", "x_1", "g_shunt", "b_shunt"];
const T2_FIELDS = ["u_1", "u_2"];
const T3_FIELDS = ["node_3", "r_2", "x_2", "r_3", "x_3", "u_3"];
const fmt = (v) => (v === null || v === undefined ? "—" : Number(v).toFixed(3));

function branchesToRows(sections = {}) {
  const empty = { node_3: "", u_1: "", u_2: "", u_3: "", r_2: "", x_2: "", r_3: "", x_3: "" };
  return Object.entries(KIND_SECTION).flatMap(([kind, key]) =>
    (sections[key] || []).map((b) => ({ ...empty, ...b, kind })));
}

function rowsToBranches(rows) {
  const out = {};
  for (const { kind, ...rest } of rows) {
    const keys = [...BRANCH_BASE, ...(kind !== "line" ? T2_FIELDS : []), ...(kind === "t3" ? T3_FIELDS : [])];
    const item = {};
    for (const k of keys) {
      const v = rest[k];
      if (v !== "" && v !== null && v !== undefined) item[k] = v;
    }
    (out[KIND_SECTION[kind]] ||= []).push(item);
  }
  return out;
}

export default function App() {
  const [caseId, setCaseId] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const guard = useCallback(async (fn) => {
    setError("");
    try { await fn(); } catch (e) { setError(e.message || String(e)); }
  }, []);
  const notify = (msg) => { setNotice(msg); setTimeout(() => setNotice(""), 2500); };
  return (
    <div className="app">
      <header>
        <h1 onClick={() => setCaseId(null)}>Расчёт установившегося режима — Ньютон–Рафсон</h1>
        {notice && <span className="notice">{notice}</span>}
      </header>
      {error && <div className="error" onClick={() => setError("")}>{error}</div>}
      {caseId === null
        ? <CaseList guard={guard} onOpen={setCaseId} />
        : <CaseEditor key={caseId} id={caseId} guard={guard} notify={notify} onBack={() => setCaseId(null)} />}
    </div>
  );
}

function CaseList({ guard, onOpen }) {
  const [cases, setCases] = useState([]);
  const fileRef = useRef(null);
  const refresh = async () => setCases(await api.cases());
  useEffect(() => { guard(refresh); }, [guard]);
  const create = () => {
    const name = prompt("Название новой схемы:");
    if (name) guard(async () => { await api.createCase(name); await refresh(); });
  };
  const onFile = (e) => {
    const file = e.target.files[0];
    if (file) guard(async () => { await api.importCase(file); await refresh(); });
    e.target.value = "";
  };
  return (
    <section>
      <div className="toolbar">
        <button onClick={create}>Новая схема</button>
        <button onClick={() => fileRef.current.click()}>Импорт JSON</button>
        <input ref={fileRef} type="file" accept=".json,application/json" hidden onChange={onFile} />
      </div>
      <table>
        <thead><tr><th>Схема</th><th>Создана</th><th>Расчётов</th><th></th></tr></thead>
        <tbody>
          {cases.map((c) => (
            <tr key={c.id}>
              <td><a onClick={() => onOpen(c.id)}>{c.name}</a></td>
              <td>{new Date(c.created_at).toLocaleString()}</td>
              <td>{c.runs_count}</td>
              <td className="row-actions">
                <button onClick={() => guard(() => exportCase(c.id, c.name))}>Экспорт</button>
                <button className="danger" onClick={() => {
                  if (confirm(`Удалить схему «${c.name}»?`))
                    guard(async () => { await api.deleteCase(c.id); await refresh(); });
                }}>Удалить</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {cases.length === 0 && <p>Схем нет. Создайте новую или импортируйте JSON (например, data/test_data_1.json).</p>}
    </section>
  );
}

function CaseEditor({ id, guard, notify, onBack }) {
  const [name, setName] = useState("");
  const [params, setParams] = useState({ accuracy: 0.01, max_iterations: 100, damping: 1 });
  const [loads, setLoads] = useState([]);
  const [nodes, setNodes] = useState([]);
  const [branches, setBranches] = useState([]);
  const [runs, setRuns] = useState([]);
  const [run, setRun] = useState(null);
  const [tab, setTab] = useState("nodes");

  useEffect(() => {
    guard(async () => {
      const d = await api.getCase(id);
      setName(d.name);
      setParams(d.data["CALCULATION PARAMETERS"]);
      setLoads(d.data.LOADS || []);
      setNodes(d.data.NODES || []);
      setBranches(branchesToRows(d.data.BRANCHES));
      setRuns(d.runs);
    });
  }, [id, guard]);

  const buildPayload = () => ({
    name,
    data: {
      "CALCULATION PARAMETERS": params,
      LOADS: loads,
      NODES: nodes.map((n) => {
        const copy = { ...n };
        if (copy.u_setpoint === "" || copy.u_setpoint === null) delete copy.u_setpoint;
        return copy;
      }),
      BRANCHES: rowsToBranches(branches),
    },
  });

  const save = async (silent) => {
    await api.updateCase(id, buildPayload());
    if (!silent) notify("Сохранено");
  };
  const calculate = () => guard(async () => {
    await save(true);
    const r = await api.calculate(id);
    setRun(r);
    setRuns((await api.getCase(id)).runs);
    setTab("results");
    if (!r.converged) throw new Error(`Расчёт не сошёлся: ${r.error}`);
    notify("Расчёт завершён");
  });
  const doExport = (withRun) => guard(async () => {
    await save(true);
    await exportCase(id, name, withRun ? run?.id : undefined);
  });

  const loadNames = loads.map((l) => l.load_name);
  const nodeNames = nodes.map((n) => n.node_name);
  const loadCols = [
    { key: "load_name", label: "Имя", type: "text" },
    { key: "p_0", label: "P₀, МВт" }, { key: "q_0", label: "Q₀, Мвар" },
    { key: "z_p", label: "z_p" }, { key: "i_p", label: "i_p" }, { key: "p_p", label: "p_p" },
    { key: "z_q", label: "z_q" }, { key: "i_q", label: "i_q" }, { key: "p_q", label: "p_q" },
    { key: "u_0", label: "U₀, кВ" },
  ];
  const nodeCols = [
    { key: "node_name", label: "Имя", type: "text" },
    { key: "type_node", label: "Тип", type: "select", options: ["pq", "pu", "slack"] },
    { key: "type_node_current", label: "Тип тек.", type: "select", options: ["pq", "pu", "slack"] },
    { key: "u_base", label: "U баз, кВ" }, { key: "u_magnitude", label: "U, кВ" },
    { key: "u_angle", label: "δ, рад" }, { key: "u_setpoint", label: "U уст., кВ" },
    { key: "g_shunt", label: "g шунт, См" }, { key: "b_shunt", label: "b шунт, См" },
    { key: "p_gen", label: "P ген, МВт" }, { key: "q_gen", label: "Q ген, Мвар" },
    { key: "q_min", label: "Q min, Мвар" }, { key: "q_max", label: "Q max, Мвар" },
    { key: "loads", label: "Нагрузки", type: "multi", options: loadNames },
  ];
  const branchCols = [
    { key: "branch_name", label: "Имя", type: "text" },
    { key: "kind", label: "Тип", type: "select", options: ["line", "t2", "t3"] },
    { key: "node_1", label: "Узел 1", type: "select", options: nodeNames },
    { key: "node_2", label: "Узел 2", type: "select", options: nodeNames },
    { key: "node_3", label: "Узел 3", type: "select", options: nodeNames, enabled: (r) => r.kind === "t3" },
    { key: "r_1", label: "r₁, Ом" }, { key: "x_1", label: "x₁, Ом" },
    { key: "g_shunt", label: "g, См" }, { key: "b_shunt", label: "b, См" },
    { key: "u_1", label: "U₁, кВ", enabled: (r) => r.kind !== "line" },
    { key: "u_2", label: "U₂, кВ", enabled: (r) => r.kind !== "line" },
    { key: "r_2", label: "r₂, Ом", enabled: (r) => r.kind === "t3" },
    { key: "x_2", label: "x₂, Ом", enabled: (r) => r.kind === "t3" },
    { key: "r_3", label: "r₃, Ом", enabled: (r) => r.kind === "t3" },
    { key: "x_3", label: "x₃, Ом", enabled: (r) => r.kind === "t3" },
    { key: "u_3", label: "U₃, кВ", enabled: (r) => r.kind === "t3" },
  ];
  const newLoad = (rows) => ({ load_name: `Load_${rows.length + 1}`, p_0: 10, q_0: 5,
    z_p: 0, i_p: 0, p_p: 1, z_q: 0, i_q: 0, p_q: 1, u_0: 110 });
  const newNode = (rows) => ({ node_name: `Node_${rows.length + 1}`, type_node: "pq", type_node_current: "pq",
    u_base: 110, u_magnitude: 110, u_angle: 0, u_setpoint: "", g_shunt: 0, b_shunt: 0,
    p_gen: 0, q_gen: 0, q_min: 0, q_max: 0, loads: [] });
  const newBranch = (rows) => ({ branch_name: `Branch_${rows.length + 1}`, kind: "line",
    node_1: nodeNames[0] || "", node_2: nodeNames[1] || "", node_3: nodeNames[2] || "",
    r_1: 1, x_1: 10, g_shunt: 0, b_shunt: 0, u_1: 110, u_2: 10, u_3: 6, r_2: 1, x_2: 10, r_3: 1, x_3: 10 });
  const paramLabels = { accuracy: "Точность, МВт/Мвар", max_iterations: "Макс. итераций", damping: "Демпфирование (0…1)" };

  return (
    <section>
      <div className="toolbar">
        <button onClick={onBack}>← К списку</button>
        <input className="case-name" value={name} onChange={(e) => setName(e.target.value)} />
        <button onClick={() => guard(() => save())}>Сохранить</button>
        <button className="primary" onClick={calculate}>Рассчитать</button>
        <button onClick={() => doExport(false)}>Экспорт JSON</button>
      </div>
      <div className="tabs">
        {[["params", "Параметры"], ["loads", "Нагрузки"], ["nodes", "Узлы"], ["branches", "Ветви"], ["results", "Результаты"]]
          .map(([k, l]) => <button key={k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>{l}</button>)}
      </div>
      {tab === "params" && (
        <div className="params">
          {Object.entries(paramLabels).map(([k, label]) => (
            <label key={k}>{label}
              <input type="number" step="any" value={params[k]}
                     onChange={(e) => setParams({ ...params, [k]: Number(e.target.value) })} />
            </label>
          ))}
        </div>
      )}
      {tab === "loads" && <EditableTable columns={loadCols} rows={loads} onChange={setLoads} newRow={newLoad} addLabel="Добавить нагрузку" />}
      {tab === "nodes" && <EditableTable columns={nodeCols} rows={nodes} onChange={setNodes} newRow={newNode} addLabel="Добавить узел" />}
      {tab === "branches" && <EditableTable columns={branchCols} rows={branches} onChange={setBranches} newRow={newBranch} addLabel="Добавить ветвь" />}
      {tab === "results" && (
        <div>
          <div className="toolbar">
            <select value={run?.id || ""} onChange={(e) => guard(async () => setRun(await api.getRun(Number(e.target.value))))}>
              <option value="" disabled>Выберите расчёт</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  №{r.id} — {new Date(r.created_at).toLocaleString()} {r.converged ? "✓" : "✗"}
                </option>
              ))}
            </select>
            {run?.converged && <button onClick={() => doExport(true)}>Экспорт результатов JSON</button>}
          </div>
          {run ? <RunView run={run} /> : <p>Выполните расчёт или выберите сохранённый.</p>}
        </div>
      )}
    </section>
  );
}

function ViewTable({ cols, rows }) {
  return (
    <table>
      <thead><tr>{cols.map(([k, l]) => <th key={k}>{l}</th>)}</tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>{cols.map(([k]) => <td key={k}>{typeof r[k] === "number" ? fmt(r[k]) : r[k] ?? "—"}</td>)}</tr>
        ))}
      </tbody>
    </table>
  );
}

function RunView({ run }) {
  if (!run.converged) return <div className="error">Расчёт не сошёлся: {run.error}</div>;
  return (
    <div>
      <p><b>Суммарные потери:</b> ΔP = {fmt(run.total_losses.dp)} МВт, ΔQ = {fmt(run.total_losses.dq)} Мвар</p>
      <h3>Напряжения узлов</h3>
      <ViewTable
        cols={[["node_name", "Узел"], ["type_node_current", "Тип"], ["u_magnitude", "U, кВ"], ["u_angle_deg", "δ, град"], ["q_gen", "Q ген, Мвар"]]}
        rows={run.nodes.map((n) => ({ ...n, u_angle_deg: (n.u_angle * 180) / Math.PI }))}
      />
      <h3>Мощности балансирующих узлов</h3>
      <ViewTable cols={[["node_name", "Узел"], ["p", "P, МВт"], ["q", "Q, Мвар"]]} rows={run.slack_powers} />
      <h3>Потоки и потери в ветвях</h3>
      <ViewTable
        cols={[["branch_name", "Ветвь"], ["p_1", "P₁, МВт"], ["q_1", "Q₁, Мвар"], ["p_2", "P₂, МВт"], ["q_2", "Q₂, Мвар"],
               ["p_3", "P₃, МВт"], ["q_3", "Q₃, Мвар"], ["dp", "ΔP, МВт"], ["dq", "ΔQ, Мвар"]]}
        rows={run.branch_flows}
      />
    </div>
  );
}
