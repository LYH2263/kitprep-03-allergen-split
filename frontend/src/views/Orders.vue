<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { api, post, ApiError } from '../api'
import { selectedOrderId, selectOrder, ensureSelectedOrder } from '../selectedOrder'

const orders = ref<any[]>([])
const lines = ref<any[]>([])
const busy = ref(false)
const result = ref<any>(null)
const error = ref('')

async function loadLines() {
  lines.value = []
  result.value = null
  error.value = ''
  if (selectedOrderId.value == null) return
  lines.value = await api('/orders/' + selectedOrderId.value + '/lines')
}

async function generate() {
  if (selectedOrderId.value == null || busy.value) return
  busy.value = true
  error.value = ''
  try {
    result.value = await post('/prep/run?order_id=' + selectedOrderId.value)
  } catch (e: any) {
    error.value = e instanceof ApiError ? e.message : '生成失败'
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  orders.value = await api('/orders')
  ensureSelectedOrder(orders.value)
  await loadLines()
})

watch(selectedOrderId, loadLines)
</script>
<template>
  <h1>订单芯片</h1>
  <p class="sub">门店要货 · 点芯片选单 · 与备料台共用同一套两本账，重复/抢点只生成一次</p>
  <div class="kp-chips" style="margin-bottom:1rem">
    <span v-for="o in orders" :key="o.id" class="kp-chip"
          :style="{ cursor: 'pointer' }"
          :class="{ 'router-link-active': o.id === selectedOrderId }"
          @click="selectOrder(o.id)">
      {{ o.code }} · {{ o.outlet }} · {{ o.status }}
    </span>
  </div>
  <button class="btn" :disabled="busy || selectedOrderId == null" @click="generate" style="margin-bottom:0.85rem">
    {{ busy ? '生成中…' : '生成备料单' }}
  </button>
  <p v-if="error" class="badge badge-bad" style="display:inline-block;margin:0 0 0.85rem 0.5rem">{{ error }}</p>
  <div v-if="result" class="card" style="margin-bottom:0.85rem;max-width:560px">
    <strong>运行 #{{ result.id }}</strong>：主缺料贴 {{ result.stats.main_count }} 行 ·
    敏料专册 {{ result.stats.allergen_count }} 行（同一套两本账，已冻结）
    <RouterLink to="/prep" class="kp-chip" style="margin-left:0.5rem">去备料台查看 →</RouterLink>
  </div>
  <div class="kp-worksheet">
    <h2>订单行</h2>
    <table>
      <thead><tr><th>菜品</th><th>份数</th></tr></thead>
      <tbody>
        <tr v-for="l in lines" :key="l.id"><td>{{ l.dish_name }}</td><td>{{ l.portions }}</td></tr>
      </tbody>
    </table>
  </div>
</template>
