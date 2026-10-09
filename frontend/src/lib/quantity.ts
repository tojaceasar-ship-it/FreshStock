const discreteUnits = new Set(['szt', 'opak', 'karton'])

export function quantityStep(unit?: string) {
  return discreteUnits.has(unit || '') ? '1' : '0.001'
}

export function parseQuantity(value: string | number, unit?: string, allowZero = false) {
  const parsed = typeof value === 'number' ? value : Number(value.replace(',', '.'))
  if (!Number.isFinite(parsed) || parsed < 0 || (!allowZero && parsed === 0)) {
    throw new Error(allowZero ? 'Ilość nie może być ujemna' : 'Ilość musi być dodatnia')
  }
  if (discreteUnits.has(unit || '') && !Number.isInteger(parsed)) {
    throw new Error(`Jednostka ${unit} wymaga ilości całkowitej`)
  }
  if (!Number.isInteger(parsed * 1000)) {
    throw new Error('Ilość może mieć maksymalnie 3 miejsca po przecinku')
  }
  return parsed
}
