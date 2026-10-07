import { ref } from 'vue'

// 订单页与备料台共用的当前订单；硬编码 order_id=1 的替代。
const storage_key = 'kp_order_id'
const stored = Number(sessionStorage.getItem(storage_key))
export const selectedOrderId = ref<number | null>(stored > 0 ? stored : null)

export function selectOrder(id: number | null) {
  selectedOrderId.value = id
  if (id == null) sessionStorage.removeItem(storage_key)
  else sessionStorage.setItem(storage_key, String(id))
}

// /orders 加载后：没选过则默认第一单
export function ensureSelectedOrder(orders: Array<{ id: number }>) {
  if (selectedOrderId.value == null && orders.length) selectOrder(orders[0].id)
}
