<template>
  <section class="page" data-module="stockin">
    <header class="page-head">
      <div>
        <h2>样品流转管理</h2>
        <p class="page-desc">维护流转记录，围绕流转编号、关联样品、流转环节、交接人做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记流转记录</button>
        <button class="btn" type="button" @click="exportRows">导出样品流转清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      <span class="filter-hint">流转环节可选：{{ flowSteps.join('、') }}</span>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无样品流转数据，可先登记流转记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条样品流转记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/stockin'
const columns = ["流转编号", "关联样品", "流转环节", "交接人", "接收人", "交接时间", "存放位置", "流转状态"]
// 动作与流转环节默认走后端 /options 下发的共用集合；接口不可用时退回本地兜底值
const DEFAULT_ACTIONS = ["发起交接", "确认接收", "取消交接", "退回样品"]
const DEFAULT_STEPS = ["采样接收", "入库暂存", "分发检测", "留样归档"]
const actions = ref<string[]>([...DEFAULT_ACTIONS])
const flowSteps = ref<string[]>([...DEFAULT_STEPS])
const statuses = ["待交接", "流转中", "已接收", "已退回"]
const stats = [{"label": "待交接记录", "value": 0}, {"label": "流转中样品", "value": 0}, {"label": "退回次数", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '流转记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    if (!response.ok) {
      throw new Error('样品流转动作未生效，请稍后重试')
    }
    const payload = await response.json()
    if (!payload.ok) {
      throw new Error(payload.message || '样品流转动作未生效')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '样品流转操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('流转记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '样品流转列表读取失败'
  }
}

async function loadOptions() {
  try {
    const response = await request(`${ENDPOINT}/options`)
    if (!response.ok) return
    const payload = await response.json()
    if (Array.isArray(payload.actions) && payload.actions.length) {
      actions.value = payload.actions
    }
    if (Array.isArray(payload.flowSteps) && payload.flowSteps.length) {
      flowSteps.value = payload.flowSteps
    }
  } catch {
    // 选项拉取失败不阻塞列表，沿用本地兜底值
  }
}

onMounted(() => {
  void loadOptions()
  void reload()
})
</script>
