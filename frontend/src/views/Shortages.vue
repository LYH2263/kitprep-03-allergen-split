<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { selectedOrderId, selectOrder, ensureSelectedOrder } from '../selectedOrder'

const orders = ref<any[]>([])
const mainRows = ref<any[]>([])
const allergenRows = ref<any[]>([])
const stats = ref<any>({})

async function load() {
  if (selectedOrderId.value == null) return
  const res = await api('/prep/shortages?order_id=' + selectedOrderId.value)
  mainRows.value = res.main_shortages || []
  allergenRows.value = res.allergen_shortages || []
  stats.value = res.stats || {}
}

onMounted(async () => {
  orders.value = await api('/orders')
  ensureSelectedOrder(orders.value)
  await load()
})

watch(selectedOrderId, load)
</script>
<template>
  <h1>缺料便利贴</h1>
  <p class="sub">shortage = need − stock（仅正数）· 含敏缺料只进敏料专册；分册错误整次回滚，与结存够不够无关</p>
  <div class="kp-chips" style="margin-bottom:1rem" v-if="orders.length">
    <span v-for="o in orders" :key="o.id" class="kp-chip"
          :style="{ cursor: 'pointer' }"
          :class="{ 'router-link-active': o.id === selectedOrderId }"
          @click="selectOrder(o.id)">
      {{ o.code }} · {{ o.outlet }}
    </span>
  </div>
  <div style="display:flex;gap:1rem;flex-wrap:wrap;align-items:flex-start">
    <div style="flex:1;min-width:300px">
      <div class="kp-shortage-sticky" style="max-width:420px;transform:rotate(-1deg);margin-bottom:1rem">
        <h2>⚠ 主缺料贴 {{ stats.main_count ?? 0 }} · 合计 {{ mainRows.reduce((s, r) => s + (r.shortage || 0), 0).toFixed(3) }}</h2>
        <div v-for="r in mainRows" :key="r.ingredient_id" class="kp-shortage-item">
          <span>{{ r.ingredient_name }}</span>
          <span class="kp-qty">−{{ r.shortage }} {{ r.unit }}</span>
        </div>
        <p v-if="!mainRows.length" style="font-size:0.8rem;margin:0.5rem 0 0">主贴无缺料</p>
      </div>
      <div class="card">
        <table>
          <thead><tr><th>原料</th><th>需求</th><th>结存</th><th>缺料</th><th>单位</th></tr></thead>
          <tbody>
            <tr v-for="r in mainRows" :key="r.ingredient_id">
              <td>{{ r.ingredient_name }}</td><td>{{ r.need_qty }}</td><td>{{ r.stock_qty }}</td>
              <td><span class="badge badge-bad">{{ r.shortage }}</span></td><td>{{ r.unit }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <div style="flex:1;min-width:300px">
      <div class="kp-shortage-sticky" style="max-width:420px;transform:rotate(1deg);margin-bottom:1rem;border-color:rgba(196,122,44,0.55)">
        <h2>🌿 敏料专册 {{ stats.allergen_count ?? 0 }} · 合计 {{ allergenRows.reduce((s, r) => s + (r.shortage || 0), 0).toFixed(3) }}</h2>
        <div v-for="r in allergenRows" :key="r.ingredient_id" class="kp-shortage-item">
          <span>{{ r.ingredient_name }} <span class="badge badge-warn">含敏</span></span>
          <span class="kp-qty">−{{ r.shortage }} {{ r.unit }}</span>
        </div>
        <p v-if="!allergenRows.length" style="font-size:0.8rem;margin:0.5rem 0 0">敏料专册为空（无含敏缺料）</p>
      </div>
      <div class="card">
        <table>
          <thead><tr><th>原料</th><th>需求</th><th>结存</th><th>缺料</th><th>单位</th></tr></thead>
          <tbody>
            <tr v-for="r in allergenRows" :key="r.ingredient_id">
              <td>{{ r.ingredient_name }} <span class="badge badge-warn">含敏</span></td>
              <td>{{ r.need_qty }}</td><td>{{ r.stock_qty }}</td>
              <td><span class="badge badge-bad">{{ r.shortage }}</span></td><td>{{ r.unit }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
