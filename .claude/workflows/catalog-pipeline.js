export const meta = {
  name: 'catalog-pipeline',
  description: 'Прогон шагов NN-CATALOG-*.md: designer → generator → (reviewer ‖ ui-reviewer) совещательно → git/PR/STATE через steward.',
  whenToUse: 'Явный запуск смены по планам Catalog. args: { plansDir, state, branch, cyclesMax, steps, maxSteps }. plansDir и state ОБЯЗАТЕЛЬНЫ (например plansDir: "docs/plan/<RUN_NAME>/", state: ".claude/state/<RUN_NAME>.json") — без них скрипт сразу останавливается.',
  phases: [
    { title: 'Preflight', model: 'sonnet' },
    { title: 'Design', model: 'opus' },
    { title: 'Generate', model: 'sonnet' },
    { title: 'Review', model: 'opus' },
    { title: 'UI review', model: 'sonnet' },
    { title: 'Finalize', model: 'sonnet' },
  ],
}

// ---------------------------------------------------------------- параметры

const A = args || {}

// plansDir и state — без дефолтов намеренно. Любой дефолт здесь молча уводит прогон
// не туда: чужой путь состояния затирается поверх, а несуществующая папка планов
// выглядит как штатная «пустая очередь». Единственный вызывающий (/catalog-full-run)
// всегда передаёт оба явно, так что дефолт обслуживать некого — лучше внятный стоп.
const missing = []
if (!A.plansDir) missing.push('args.plansDir (например "docs/plan/<RUN_NAME>/")')
if (!A.state) missing.push('args.state (например ".claude/state/<RUN_NAME>.json")')
if (missing.length) {
  const reason = `не заданы обязательные аргументы: ${missing.join('; ')}`
  log(`catalog-pipeline: ${reason} — запуск отменён, ничего не тронуто`)
  return { stopped: 'args', reason }
}

const PLANS_DIR = A.plansDir.replace(/\/*$/, '/')
const STATE = A.state
const BRANCH = A.branch || null
const CYCLES_MAX = A.cyclesMax || 5
const ONLY = A.steps || null
const MAX_STEPS = A.maxSteps || 0

// Модели и effort ролей — единый источник правды. В .claude/agents/catalog-*.md
// поля model: нет намеренно. Режимов/пресетов нет: конфигурация одна, менять её —
// значит менять этот объект, а не передавать args.
const ROLES = {
  designer: { model: 'opus', effort: 'high' },
  generator: { model: 'sonnet', effort: 'high' },
  reviewer: { model: 'opus', effort: 'high' },
  uiReviewer: { model: 'sonnet', effort: 'high' },
  steward: { model: 'sonnet', effort: 'medium' },
}

// ---------------------------------------------------------------- схемы

const ISSUE = {
  type: 'object',
  required: ['severity', 'location', 'problem'],
  properties: {
    severity: { type: 'string', enum: ['Critical', 'Medium', 'Low'] },
    location: { type: 'string' },
    problem: { type: 'string' },
  },
}

const REVIEW_SCHEMA = {
  type: 'object',
  required: ['verdict', 'issues'],
  properties: {
    verdict: { type: 'string', enum: ['APPROVED', 'CHANGES_REQUESTED'] },
    issues: { type: 'array', items: ISSUE },
    checks: { type: 'string' },
  },
}

const PREFLIGHT_SCHEMA = {
  type: 'object',
  required: ['ok', 'steps'],
  properties: {
    ok: { type: 'boolean' },
    reason: { type: 'string' },
    branch: { type: 'string' },
    prNumber: { type: ['integer', 'null'] },
    prUrl: { type: ['string', 'null'] },
    steps: {
      type: 'array',
      items: {
        type: 'object',
        required: ['file', 'kind', 'ticket', 'blockedBy', 'designPath'],
        properties: {
          file: { type: 'string' },
          kind: { type: 'string', enum: ['code', 'ui'] },
          // ticket + blockedBy — гейт зависимостей: упавший или пропущенный шаг
          // не должен пускать дальше зависимые. Опциональные поля тихо убивают
          // гейт (steward вправе их не вернуть), поэтому required.
          ticket: { type: 'string' },
          blockedBy: { type: 'array', items: { type: 'string' } },
          // designPath: null для code-шага и для ui-шага без готовой спеки.
          designPath: { type: ['string', 'null'] },
        },
      },
    },
  },
}

const GEN_SCHEMA = {
  type: 'object',
  required: ['summary', 'checks', 'handoff'],
  properties: {
    summary: { type: 'string' },
    filesChanged: { type: 'array', items: { type: 'string' } },
    checks: { type: 'string' },
    addressed: { type: 'array', items: { type: 'string' } },
    handoff: { type: 'string' },
  },
}

const DESIGN_SCHEMA = {
  type: 'object',
  required: ['designPath', 'summary'],
  properties: {
    designPath: { type: 'string' },
    summary: { type: 'string' },
  },
}

const SHA_SCHEMA = {
  type: 'object',
  required: ['ok', 'sha'],
  properties: { ok: { type: 'boolean' }, sha: { type: 'string' }, reason: { type: 'string' } },
}

const FINALIZE_SCHEMA = {
  type: 'object',
  required: ['ok'],
  properties: {
    ok: { type: 'boolean' },
    commit: { type: ['string', 'null'] },
    prUrl: { type: ['string', 'null'] },
    prNumber: { type: ['integer', 'null'] },
    checks: { type: 'string' },
    reason: { type: 'string' },
  },
}

// ---------------------------------------------------------------- помощники

const CTX = `PLANS_DIR=${PLANS_DIR}\nSTATE=${STATE}\nBRANCH=${BRANCH || '<из STATE или укажи явно>'}`

function fmtIssues(tag, issues) {
  if (!issues || !issues.length) return []
  return issues.map(i => `- [${tag}] [${i.severity}] ${i.location} — ${i.problem}`)
}

function issuesText(lines) {
  return lines.length ? lines.join('\n') : 'нет'
}

function blocking(issues) {
  return (issues || []).filter(i => i.severity === 'Critical' || i.severity === 'Medium')
}

// ---------------------------------------------------------------- фаза 0

phase('Preflight')
log(`модели: designer=${ROLES.designer.model} generator=${ROLES.generator.model} reviewer=${ROLES.reviewer.model} ui=${ROLES.uiReviewer.model} steward=${ROLES.steward.model}`)

const pre = await agent(
  `Задача: preflight.\n${CTX}\n\n` +
  `Проверь дерево и gh, подготовь ветку, прочитай/создай STATE и собери очередь шагов по контракту из своей роли. ` +
  `Ничего не коммить и не пушить.`,
  { label: 'preflight', phase: 'Preflight', agentType: 'catalog-steward', schema: PREFLIGHT_SCHEMA, ...ROLES.steward },
)

if (!pre || !pre.ok) {
  const why = pre ? pre.reason : 'steward не вернул результат'
  log(`preflight провалился: ${why}`)
  return { stopped: 'preflight', reason: why }
}

let queue = pre.steps || []
if (ONLY && ONLY.length) queue = queue.filter(s => ONLY.indexOf(s.file) !== -1)
if (MAX_STEPS > 0 && queue.length > MAX_STEPS) {
  log(`очередь обрезана до ${MAX_STEPS} из ${queue.length} шагов (maxSteps); остальные не тронуты`)
  queue = queue.slice(0, MAX_STEPS)
}

if (!queue.length) {
  log('очередь пуста — нечего прогонять')
  return { stopped: 'empty-queue', branch: pre.branch, prUrl: pre.prUrl }
}

const uiCount = queue.filter(s => s.kind === 'ui').length
log(`шагов в очереди: ${queue.length} (ui: ${uiCount}) · ветка ${pre.branch} · потолок циклов ${CYCLES_MAX}`)

// ---------------------------------------------------------------- шаги
// Строго последовательно: все шаги делят одну ветку и одно рабочее дерево,
// поэтому parallel()/pipeline() здесь были бы гонкой за git-индекс, а не ускорением.

const results = []
const failedTickets = []

// Блокирует зависимых и по упавшему шагу, и по пропущенному: в цепочке A → B → C,
// где A упал, а B пропущен как заблокированный, C тоже не должен стартовать.
function markBlocking(ticket) {
  if (ticket && failedTickets.indexOf(ticket) === -1) failedTickets.push(ticket)
}
let prUrl = pre.prUrl || null
let prNumber = pre.prNumber || null

for (let n = 0; n < queue.length; n++) {
  const step = queue[n]
  const stem = step.file.replace(/\.md$/, '')
  const isUi = step.kind === 'ui'
  const tag = `${n + 1}/${queue.length} ${stem}`

  const blockedBy = (step.blockedBy || []).filter(t => failedTickets.indexOf(t) !== -1)
  if (blockedBy.length) {
    log(`${tag}: пропущен — зависит от упавшего/пропущенного ${blockedBy.join(', ')}`)
    results.push({ step: step.file, status: 'skipped', reason: `blocked_by ${blockedBy.join(', ')}` })
    markBlocking(step.ticket)
    continue
  }

  const sha = await agent(
    `Задача: base_sha.\n${CTX}\nSTEP=${step.file}`,
    { label: `sha:${stem}`, phase: 'Preflight', agentType: 'catalog-steward', schema: SHA_SCHEMA, ...ROLES.steward },
  )
  if (!sha || !sha.ok) {
    log(`${tag}: не удалось снять base_sha — шаг пропущен`)
    results.push({ step: step.file, status: 'failed', reason: 'base_sha' })
    markBlocking(step.ticket)
    continue
  }
  const base = sha.sha

  // Фаза дизайна — один раз до цикла, только для UI-шага.
  let designPath = step.designPath || null
  if (isUi && !designPath) {
    const d = await agent(
      `PLAN=${PLANS_DIR}${step.file}\nDESIGN=${PLANS_DIR}${stem}.design.md\n\n` +
      `Спроектируй UI шага и запиши дизайн-спеку по контракту своей роли.`,
      { label: `design:${stem}`, phase: 'Design', agentType: 'catalog-designer', schema: DESIGN_SCHEMA, ...ROLES.designer },
    )
    designPath = d ? d.designPath : null
    if (!designPath) log(`${tag}: дизайнер не вернул спеку — шаг пойдёт без DESIGN`)
  }

  // Цикл generator → ревьюеры → финализация. Ревью **совещательное**: вердикт
  // APPROVED/CHANGES_REQUESTED коммит не блокирует. Единственный жёсткий гейт шага —
  // зелёные финальные проверки в finalize у стюарда; красные возвращают шаг в цикл,
  // пока не исчерпан лимит. Замечания ревьюеров копятся в advisory, уходят в STATE
  // и в итог прогона, а на повторном цикле отдаются генератору вместе с причиной —
  // починить их заодно дёшево, но само по себе замечание шаг не задерживает.
  let issues = []
  let advisory = []
  let handoff = 'первый цикл, предыдущей работы нет'
  let cycle = 0
  let lastChecks = ''
  let finalized = null

  while (cycle < CYCLES_MAX) {
    cycle++
    log(`${tag}: цикл ${cycle}/${CYCLES_MAX}`)

    const genPrompt =
      `PLAN=${PLANS_DIR}${step.file}\n` +
      (designPath ? `DESIGN=${designPath}\n` : '') +
      `DIFF_BASE=${base}\nCYCLE=${cycle}\n\n` +
      `ISSUES:\n${issuesText(issues)}\n\n` +
      `PRIOR_WORK:\n${handoff}\n\n` +
      `Реализуй шаг и доведи проверки до зелёного. Не трогай git-состояние. ` +
      `Обязательно заполни handoff — это единственная память шага для следующего цикла.`

    const gen = await agent(genPrompt, {
      label: `gen:${stem}#${cycle}`, phase: 'Generate',
      agentType: 'catalog-generator', schema: GEN_SCHEMA, ...ROLES.generator,
    })
    if (!gen) {
      log(`${tag}: генератор умер на цикле ${cycle}`)
      break
    }
    handoff = gen.handoff || handoff

    // Оба ревьюера readonly и независимы — единственное место, где параллель безопасна.
    const reviewPrompt = suffix =>
      `PLAN=${PLANS_DIR}${step.file}\n` +
      (designPath ? `DESIGN=${designPath}\n` : '') +
      `DIFF_BASE=${base}\nCYCLE=${cycle}\n\nPRIOR_ISSUES:\n${issuesText(issues)}\n\n${suffix}`

    const jobs = [
      () => agent(reviewPrompt('Отревьюй дифф шага против плана и ADR, прогони проверки, верни вердикт.'), {
        label: `review:${stem}#${cycle}`, phase: 'Review',
        agentType: 'catalog-reviewer', schema: REVIEW_SCHEMA, ...ROLES.reviewer,
      }),
    ]
    if (isUi && designPath) {
      jobs.push(() => agent(reviewPrompt('Сверь реализацию UI с дизайн-спекой статически, верни вердикт.'), {
        label: `ui:${stem}#${cycle}`, phase: 'UI review',
        agentType: 'catalog-ui-reviewer', schema: REVIEW_SCHEMA, ...ROLES.uiReviewer,
      }))
    }

    const [code, ui] = await parallel(jobs)

    // Вердикт — справочный. Мёртвый ревьюер больше не держит шаг: он лишь остаётся
    // без замечаний, и это видно в логе.
    const codeVerdict = code ? code.verdict : 'нет ответа'
    const uiVerdict = (isUi && designPath) ? (ui ? ui.verdict : 'нет ответа') : '—'
    lastChecks = (code && code.checks) || gen.checks || ''

    issues = fmtIssues('CODE', code && code.issues).concat(fmtIssues('UI', ui && ui.issues))
    const hard = blocking(code && code.issues).length + blocking(ui && ui.issues).length
    for (const line of issues) if (advisory.indexOf(line) === -1) advisory.push(line)

    log(`${tag}: ревью совещательно · code=${codeVerdict} ui=${uiVerdict} · замечаний ${issues.length} (Critical/Medium ${hard})`)

    // Финализация — единственная точка коммита шага и единственный жёсткий гейт.
    const fin = await agent(
      `Задача: finalize.\n${CTX}\nSTEP=${step.file}\nTICKET=${step.ticket}\n` +
      `PR_NUMBER=${prNumber === null ? 'нет' : prNumber}\n\n` +
      `REVIEW_NOTES — совещательные замечания ревью, коммит они НЕ блокируют. ` +
      `Запиши их в STATE шага как есть и не пытайся чинить:\n${issuesText(advisory)}\n\n` +
      `Прогони финальные проверки, закоммить только файлы шага, запушь, при необходимости создай PR, обнови STATE.`,
      { label: `finalize:${stem}#${cycle}`, phase: 'Finalize', agentType: 'catalog-steward', schema: FINALIZE_SCHEMA, ...ROLES.steward },
    )
    if (fin && fin.ok) {
      finalized = fin
      break
    }

    // Финальные проверки красные — не коммитим, дописываем issue и возвращаемся
    // в цикл; в fail проваливаемся только исчерпав лимит.
    const why = fin ? (fin.reason || fin.checks) : 'steward не вернул результат'
    issues = issues.concat([`- [CODE] [Critical] финальные проверки — ${why}`])
    lastChecks = (fin && fin.checks) || lastChecks
    handoff = `${handoff}\n\nЦикл ${cycle}: финальные проверки красные — ${why}. Чини в первую очередь проверки; совещательные замечания ревью — попутно, если дёшево.`
    log(
      cycle < CYCLES_MAX
        ? `${tag}: финализация отклонена — ${why} · возврат в цикл`
        : `${tag}: финализация отклонена на последнем цикле — ${why}`,
    )
  }

  if (finalized) {
    prUrl = finalized.prUrl || prUrl
    prNumber = (finalized.prNumber === null || finalized.prNumber === undefined) ? prNumber : finalized.prNumber
    log(`${tag}: done · ${finalized.commit || 'commit?'}${advisory.length ? ` · совещательных замечаний ${advisory.length}` : ''}`)
    results.push({
      step: step.file, status: 'done', cycles: cycle,
      commit: finalized.commit || null, advisory,
    })
    continue
  }

  await agent(
    `Задача: fail.\n${CTX}\nSTEP=${step.file}\nCYCLES=${cycle}\nCHECKS=${lastChecks}\n\nISSUES:\n${issuesText(issues)}`,
    { label: `fail:${stem}`, phase: 'Finalize', agentType: 'catalog-steward', ...ROLES.steward },
  )
  log(`${tag}: failed после ${cycle} циклов`)
  results.push({ step: step.file, status: 'failed', cycles: cycle, issues, advisory })
  markBlocking(step.ticket)
}

const done = results.filter(r => r.status === 'done').length
const advisoryTotal = results.reduce((n, r) => n + ((r.advisory && r.advisory.length) || 0), 0)
log(`итог: done ${done} · failed ${results.filter(r => r.status === 'failed').length} · skipped ${results.filter(r => r.status === 'skipped').length} · совещательных замечаний ${advisoryTotal}`)

return {
  branch: pre.branch,
  plansDir: PLANS_DIR,
  state: STATE,
  prUrl,
  prNumber,
  stepsDone: done,
  advisoryTotal,
  results,
}
