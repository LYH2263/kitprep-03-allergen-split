<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, patch } from '../api'

const rows = ref<any[]>([])
const dirty = ref<Record<number, boolean>>({})
const saving = ref<number | null>(null)
const error = ref('')

async function load() { rows.value = await api('/inventory') }

function toggle(r: any) {
  dirty.value[r.id] = true
  error.value = ''
}

async function save(r: any) {
  saving.value = r.id
  error.value = ''
  try {
    const updated = await patch('/inventory/' + r.id, { is_allergen: !!r.is_allergen })
    Object.assign(r, updated)
    dirty.value[r.id] = false
  } catch (e: any) {
    error.value = e?.message || '保存失败'
  } finally {
    saving.value = null
  }
}

onMounted(load)
</script>
<template>
  <h1>库存</h1>
  <p class="sub">中央厨房原料库存 · 含敏标记在此保存，下一次生成备料单时按标记拆专册；生成只记占用、不扣结存</p>
  <p v-if="error" class="badge badge-bad" style="display:inline-block;margin-bottom:0.5rem">{{ error }}</p>
  <div class="card">
    <table>
      <thead><tr><th>编码</th><th>名称</th><th>结存</th><th>占用</th><th>可用</th><th>单位</th><th>含敏</th><th></th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id">
          <td>{{ r.code }}</td>
          <td>{{ r.name }}</td>
          <td>{{ r.stock_qty }}</td>
          <td>{{ r.occupied_qty }}</td>
          <td>{{ r.available_qty }}</td>
          <td>{{ r.unit }}</td>
          <td><input type="checkbox" :checked="r.is_allergen" @change="r.is_allergen = ($event.target as HTMLInputElement).checked; toggle(r)" /></td>
          <td>
            <button class="btn" style="padding:0.15rem 0.6rem;font-size:0.72rem"
                    :disabled="saving === r.id || !dirty[r.id]" @click="save(r)">
              {{ saving === r.id ? '保存中…' : '保存' }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
