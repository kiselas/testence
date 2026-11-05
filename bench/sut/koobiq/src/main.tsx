// Conformance stand for testence.kits: one instance of every component the kit
// addresses, rendered by the real @koobiq/react-components, react-select and
// @xyflow/react packages pinned in package.json. Each control writes what it did to
// the event log (`#log`), so a conformance test checks the outcome the component
// reported, not only what the screen shows.
//
// Synthetic data only. Nothing here imitates a real product.

import '@koobiq/design-tokens/web/css-tokens.css'
import '@koobiq/react-components/style.css'

import { StrictMode, useCallback, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  Badge,
  Button,
  Checkbox,
  Input,
  InputNumber,
  Menu,
  Modal,
  Provider,
  SearchInput,
  Select,
  SidePanel,
  Tab,
  Table,
  Tabs,
  Tag,
  TagGroup,
  ToastProvider,
  Toggle,
  Tooltip,
  toast,
} from '@koobiq/react-components'
import ReactSelect from 'react-select'
import {
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

type Entry = { at: number; text: string }

let logSink: ((text: string) => void) | null = null
function log(text: string) {
  logSink?.(text)
}

// ---- react-select -----------------------------------------------------------

type Option = { value: string; label: string; isDisabled?: boolean }

const TARGET_GROUPS = [
  {
    label: 'Internal',
    options: [
      { value: 'alpha', label: 'alpha.example.test' },
      { value: 'beta', label: 'beta.example.test' },
      { value: 'gamma', label: 'gamma.example.test', isDisabled: true },
    ],
  },
  {
    label: 'External',
    options: [
      { value: 'delta', label: 'delta.example.test' },
      { value: 'epsilon', label: 'epsilon.example.test' },
    ],
  },
]
// A saved value the option list no longer offers: the component still renders a chip.
const UNAVAILABLE: Option = { value: 'retired', label: 'retired.example.test' }

function Selects() {
  const [targets, setTargets] = useState<readonly Option[]>([UNAVAILABLE])
  const [zone, setZone] = useState<Option | null>(null)
  const zones: Option[] = [
    { value: 'dmz', label: 'DMZ' },
    { value: 'lan', label: 'LAN' },
    { value: 'wan', label: 'WAN' },
  ]
  const known = new Set(TARGET_GROUPS.flatMap((g) => g.options.map((o) => o.value)))
  return (
    <section aria-label="react-select fields" className="block">
      <h2>react-select</h2>
      <label id="targets-label" htmlFor="targets-input">
        Targets
      </label>
      <ReactSelect<Option, true>
        inputId="targets-input"
        aria-labelledby="targets-label"
        className="react-select"
        classNamePrefix="react-select"
        isMulti
        closeMenuOnSelect={false}
        options={TARGET_GROUPS}
        value={targets}
        styles={{
          multiValue: (base, state) =>
            known.has(state.data.value) ? base : { ...base, outline: '1px solid #d33' },
        }}
        onChange={(value) => {
          setTargets(value)
          log(`targets: ${value.map((o) => o.value).join(',') || '-'}`)
        }}
      />
      <label id="zone-label" htmlFor="zone-input">
        Zone
      </label>
      <ReactSelect<Option, false>
        inputId="zone-input"
        aria-labelledby="zone-label"
        className="react-select"
        classNamePrefix="react-select"
        isClearable
        placeholder="Select a value"
        options={zones}
        value={zone}
        noOptionsMessage={() => 'No values available'}
        onChange={(value) => {
          setZone(value)
          log(`zone: ${value ? value.value : '-'}`)
        }}
      />
    </section>
  )
}

// ---- Koobiq form controls and overlays --------------------------------------

const ROWS = [
  { id: 'r1', name: 'router-one', state: 'active' },
  { id: 'r2', name: 'router-two', state: 'paused' },
  { id: 'r3', name: 'router-three', state: 'active' },
]

function Rows() {
  const [selected, setSelected] = useState<Set<string> | 'all'>(new Set())
  return (
    <section aria-label="Table" className="block">
      <h2>Table</h2>
      <Table
        aria-label="Routers"
        selectionMode="multiple"
        selectedKeys={selected as never}
        onSelectionChange={(keys: unknown) => {
          const next = keys === 'all' ? 'all' : new Set([...(keys as Set<string>)].map(String))
          setSelected(next)
          log(`selected: ${next === 'all' ? 'all' : [...next].sort().join(',') || '-'}`)
        }}
      >
        <Table.Header>
          <Table.Column isRowHeader>Name</Table.Column>
          <Table.Column>State</Table.Column>
          <Table.Column>Actions</Table.Column>
        </Table.Header>
        <Table.Body>
          {ROWS.map((row) => (
            <Table.Row key={row.id}>
              <Table.Cell>{row.name}</Table.Cell>
              <Table.Cell>
                <Badge variant={row.state === 'active' ? 'fade-success' : 'fade-warning'}>
                  {row.state}
                </Badge>
              </Table.Cell>
              <Table.Cell>
                <Menu
                  control={(props) => (
                    <Button {...props} variant="contrast-transparent" aria-label={`Actions of ${row.name}`}>
                      ⋯
                    </Button>
                  )}
                  onAction={(key: unknown) => log(`row ${row.id}: ${String(key)}`)}
                >
                  <Menu.Item key="edit">Edit</Menu.Item>
                  <Menu.Item key="duplicate">Duplicate</Menu.Item>
                  <Menu.Item key="delete">Delete</Menu.Item>
                </Menu>
              </Table.Cell>
            </Table.Row>
          ))}
        </Table.Body>
      </Table>
    </section>
  )
}

function Panel() {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [vlan, setVlan] = useState<number>(100)
  const [confirm, setConfirm] = useState(false)
  return (
    <section aria-label="Overlays" className="block">
      <h2>Overlays</h2>
      <Button onPress={() => setOpen(true)}>Open panel</Button>
      <Button variant="error-solid" onPress={() => setConfirm(true)}>
        Delete item
      </Button>
      <SidePanel
        isOpen={open}
        onOpenChange={(value: boolean) => {
          setOpen(value)
          if (!value) log('panel: closed')
        }}
        placement="end"
        size="medium"
      >
        <SidePanel.Header>Edit router</SidePanel.Header>
        <SidePanel.Body>
          <Input label="Name" isRequired value={name} onChange={(value: string) => setName(value)} />
          <InputNumber
            label={
              <>
                VLAN{' '}
                <span role="img" aria-label="from 1 to 4094">
                  ⓘ
                </span>
              </>
            }
            value={vlan}
            minValue={1}
            maxValue={4094}
            onChange={(value: number) => {
              setVlan(value)
              log(`vlan: ${value}`)
            }}
          />
        </SidePanel.Body>
        <SidePanel.Footer>
          <Button
            onPress={() => {
              log(`saved: name=${name}, vlan=${vlan}`)
              setOpen(false)
            }}
          >
            Save
          </Button>
          <Button variant="contrast-transparent" onPress={() => setOpen(false)}>
            Close
          </Button>
        </SidePanel.Footer>
      </SidePanel>
      <Modal isOpen={confirm} onOpenChange={setConfirm} size="small">
        <Modal.Header>Delete «router-two»</Modal.Header>
        <Modal.Body>The router and its subnets will be removed.</Modal.Body>
        <Modal.Footer>
          <Button
            variant="error-solid"
            onPress={() => {
              log('confirm: delete')
              setConfirm(false)
            }}
          >
            Delete
          </Button>
          <Button
            variant="contrast-transparent"
            onPress={() => {
              log('confirm: cancel')
              setConfirm(false)
            }}
          >
            Cancel
          </Button>
        </Modal.Footer>
      </Modal>
    </section>
  )
}

function Controls() {
  const [mode, setMode] = useState<string | null>(null)
  const [tags, setTags] = useState(['prod', 'lab'])
  return (
    <section aria-label="Controls" className="block">
      <h2>Controls</h2>
      <Checkbox onChange={(value: boolean) => log(`terms: ${value}`)}>Accept terms</Checkbox>
      <Toggle onChange={(value: boolean) => log(`notifications: ${value}`)}>Notifications</Toggle>
      <Select
        label="Mode"
        placeholder="Choose a mode"
        onSelectionChange={(keys: unknown) => {
          // Koobiq's Select reports a Set of keys, also in single selection.
          const chosen = [...(keys as Iterable<unknown>)].map(String).join(',')
          setMode(chosen || null)
          log(`mode: ${chosen || '-'}`)
        }}
      >
        <Select.Item key="fast">Fast</Select.Item>
        <Select.Item key="safe">Safe</Select.Item>
        <Select.Item key="off">Off</Select.Item>
      </Select>
      <SearchInput
        label="Search routers"
        onSubmit={(value: string) => log(`search: ${value}`)}
      />
      <Tooltip
        control={(props) => (
          <Button {...props} variant="contrast-transparent">
            Help
          </Button>
        )}
      >
        Opens the user guide
      </Tooltip>
      <Tabs aria-label="Router views" onSelectionChange={(key: unknown) => log(`tab: ${String(key)}`)}>
        <Tab key="general" title="General">
          General settings
        </Tab>
        <Tab key="routes" title="Routes">
          Static routes
        </Tab>
      </Tabs>
      <p>
        <Badge variant="fade-error" style={{ color: 'rgb(200, 30, 30)' }} data-testid="health">
          degraded
        </Badge>
      </p>
      {/* The exported Tag is TagGroup's collection item: it renders nothing alone. */}
      <TagGroup
        aria-label="Labels"
        variant="theme-fade"
        onRemove={(keys: Set<unknown>) => {
          setTags((current) => current.filter((tag) => !keys.has(tag)))
          log(`tags removed: ${[...keys].join(',')}`)
        }}
      >
        {tags.map((tag) => (
          <Tag key={tag}>{tag}</Tag>
        ))}
      </TagGroup>
    </section>
  )
}

function Toasts() {
  return (
    <section aria-label="Toasts" className="block">
      <h2>Toasts</h2>
      <Button
        onPress={() => {
          toast.add({ title: 'Router saved', caption: 'router-one', status: 'success' })
          log('toast: saved')
        }}
      >
        Show toast
      </Button>
      <Button
        onPress={() => {
          toast.add({ title: 'Save failed', caption: 'Request timed out', status: 'error' })
          log('toast: failed')
        }}
      >
        Show error
      </Button>
    </section>
  )
}

// ---- @xyflow/react ----------------------------------------------------------

function HostNode({ id, data }: { id: string; data: { label: string } }) {
  return (
    <div className="host-node">
      <Handle type="target" position={Position.Top} />
      <p>{data.label}</p>
      <Menu
        control={(props) => (
          <Button {...props} variant="contrast-transparent" aria-label={`Menu of ${data.label}`}>
            ⋮
          </Button>
        )}
        onAction={(key: unknown) => log(`node ${id}: ${String(key)}`)}
      >
        <Menu.Item key="edit">Edit</Menu.Item>
        <Menu.Item key="copy">Copy</Menu.Item>
        <Menu.Item key="delete">Delete</Menu.Item>
      </Menu>
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
}

function Flow() {
  const nodeTypes = useMemo(() => ({ host: HostNode }), [])
  const [nodes, , onNodesChange] = useNodesState([
    { id: 'h1', type: 'host', position: { x: 20, y: 20 }, data: { label: 'web-1' } },
    { id: 'h2', type: 'host', position: { x: 260, y: 20 }, data: { label: 'db-1' } },
  ])
  const [edges, , onEdgesChange] = useEdgesState([{ id: 'e1', source: 'h1', target: 'h2' }])
  return (
    <section aria-label="Scheme" className="block flow">
      <h2>Scheme</h2>
      <div style={{ width: 560, height: 220 }}>
        <ReactFlowProvider>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={nodeTypes}
            onNodeDoubleClick={(_event, node) => log(`opened: ${node.id}`)}
            proOptions={{ hideAttribution: true }}
            zoomOnDoubleClick={false}
          />
        </ReactFlowProvider>
      </div>
    </section>
  )
}

// ---- page -------------------------------------------------------------------

function Log() {
  const [entries, setEntries] = useState<Entry[]>([])
  logSink = useCallback((text: string) => {
    setEntries((current) => [...current, { at: current.length, text }])
  }, [])
  return (
    <ol id="log" aria-label="Event log">
      {entries.map((entry) => (
        <li key={entry.at}>{entry.text}</li>
      ))}
    </ol>
  )
}

// Koobiq translates its own labels ("Select all", "Close", "Remove") by locale; the
// kit must not depend on them, so the stand renders either locale on request.
const LOCALE = new URLSearchParams(location.search).get('locale') || 'en-US'

function App() {
  return (
    <Provider locale={LOCALE}>
      {/* ToastProvider is the toast region itself and renders no children. */}
      <ToastProvider />
      <main>
          <h1>Koobiq conformance stand</h1>
          <Controls />
          <Selects />
          <Rows />
          <Panel />
          <Toasts />
          <Flow />
          <Log />
      </main>
    </Provider>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
