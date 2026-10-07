<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api, post, ApiError } from '../api'
import { selectedOrderId, selectOrder, ensureSelectedOrder } from '../selectedOrder'

const tree = ref<any[]>([])
const data = ref<any>(null)
const mainShortages = ref<any[]>([])
const allergenShortages = ref<any[]>([])
const orders = ref<any[]>([])
const busy = ref(false)
const error = ref('')
const notice = ref('')

async function loadLatest() {
  if (selectedOrderId.value == null) return
  data.value = await api('/prep/latest?order_id=' + selectedOrderId.value)
  mainShortages.value = data.value.main_shortages || []
  allergenShortages.value = data.value.allergen_shortages || []
}

async function run() {
  if (selectedOrderId.value == null || busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const res = await post('/prep/run?order_id=' + selectedOrderId.value)
    data.value = res
    mainShortages.value = res.main_shortages || []
    allergenShortages.value = res.allergen_shortages || []
  } catch (e: any) {
    if (e instanceof ApiError) error.value = e.message
    else error.value = '生成失败'
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  tree.value = await api('/bom/tree')
  orders.value = await api('/orders')
  ensureSelectedOrder(orders.value)
  if (selectedOrderId.value != null) await loadLatest()
})

watch(selectedOrderId, async (id) => {
  notice.value = ''
  error.value = ''
  if (id != null) await loadLatest()
})
</script>
<template>
  <h1>备料工作台</h1>
  <p class="sub">左 BOM 树 · 中备料表 · 右主缺料贴/敏料专册 · 顶栏订单芯片 · 生成只记占用、不扣结存</p>
  <div class="kp-chips" style="margin-bottom:0.75rem" v-if="orders.length">
    <span v-for="o in orders" :key="o.id" class="kp-chip"
          :style="{ cursor: 'pointer', fontWeight: o.id === selectedOrderId ? 800 : 400 }"
          :class="{ 'router-link-active': o.id === selectedOrderId }"
          @click="selectOrder(o.id)">
      {{ o.code }} · {{ o.outlet }}
    </span>
  </div>
  <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap">
    <button class="btn" :disabled="busy || selectedOrderId == null" @click="run">
      {{ busy ? '生成中…' : '生成备料单' }}
    </button>
    <span v-if="data?.id" style="font-size:0.78rem;color:#a8b0b8">
      运行 #{{ data.id }}<template v-if="data.created_at"> · {{ data.created_at.replace('T', ' ').slice(0, 16) }}</template> · 已冻结：分册与快照不可修改
    </span>
    <span v-else style="font-size:0.78rem;color:#a8b0b8">该订单尚未生成备料单</span>
  </div>
  <p v-if="error" class="badge badge-bad" style="display:inline-block;margin:0.5rem 0 0">{{ error }}</p>
  <div class="kp-workbench" style="margin-top:0.85rem">
    <aside class="kp-bom-tree">
      <h2>菜品 / BOM</h2>
      <div v-for="d in tree" :key="d.code" class="kp-dish-node">
        <strong>{{ d.dish }}</strong>
        <span style="font-size:0.7rem;color:#8a8078">{{ d.code }}</span>
        <ul>
          <li v-for="(c,i) in d.children" :key="i">{{ c.ingredient }} · {{ c.qty }} {{ c.unit }}</li>
        </ul>
      </div>
    </aside>
    <section class="kp-worksheet" v-if="data && data.prep_lines?.length">
      <h2>备料单 · {{ data.order?.code }} · {{ data.order?.outlet }}</h2>
      <table>
        <thead><tr><th>原料</th><th>需求</th><th>结存</th><th>占用</th><th>单位</th></tr></thead>
        <tbody>
          <tr v-for="l in data.prep_lines" :key="l.ingredient_id">
            <td>
              {{ l.ingredient_name }}
              <span v-if="l.is_allergen" class="badge badge-warn" style="margin-left:0.3rem">含敏</span>
            </td>
            <td>{{ l.need_qty }}</td><td>{{ l.stock_qty }}</td><td>{{ l.occupied_qty }}</td><td>{{ l.unit }}</td>
          </tr>
        </tbody>
      </table>
    </section>
    <section v-else class="kp-worksheet"><p style="font-size:0.8rem;color:#8a8078">尚无备料单，点击「生成备料单」。</p></section>
    <div style="display:flex;flex-direction:column;gap:0.6rem">
      <aside class="kp-shortage-sticky" style="transform:rotate(-1deg)">
        <h2>⚠ 主缺料贴 {{ mainShortages.length }}</h2>
        <div v-for="r in mainShortages" :key="r.ingredient_id" class="kp-shortage-item">
          <span>{{ r.ingredient_name }}</span>
          <span class="kp-qty">−{{ r.shortage }} {{ r.unit }}</span>
        </div>
        <p v-if="!mainShortages.length" style="font-size:0.8rem;margin:0.5rem 0 0">主贴无缺料</p>
      </aside>
      <aside class="kp-shortage-sticky" style="transform:rotate(1deg);border-color:rgba(196,122,44,0.55)">
        <h2>🌿 敏料专册 {{ allergenShortages.length }}</h2>
        <div v-for="r in allergenShortages" :key="r.ingredient_id" class="kp-shortage-item">
          <span>{{ r.ingredient_name }} <span class="badge badge-warn">含敏</span></span>
          <span class="kp-qty">−{{ r.shortage }} {{ r.unit }}</span>
        </div>
        <p v-if="!allergenShortages.length" style="font-size:0.8rem;margin:0.5rem 0 0">敏料专册为空（无含敏缺料）</p>
      </aside>
    </div>
  </div>
</template>
