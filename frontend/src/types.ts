/** Тип/размер позиции (объём и т.д.) */
export interface MenuType {
  guid: string;
  name: string;
  price: number;
}

/** Позиция меню */
export interface MenuItem {
  guid: string;
  name: string;
  price?: number | null;
  typeList?: MenuType[] | null;
  recipeTypeList?: MenuType[] | null;
  supplementCategoryToFreeCount?: Record<string, number> | null;
}

/** Группа меню (ответ /api/menu — одна группа) */
export interface MenuGroup {
  guid: string;
  name: string;
  itemList?: MenuItem[];
}

/** Добавка в категории */
export interface SupplementItem {
  guid: string;
  name: string;
  defaultPrice?: number;
}

/** Категория добавок */
export interface SupplementCategory {
  guid: string;
  name: string;
  itemList?: SupplementItem[];
}

/** Элемент корзины */
export interface CartItem {
  menuItemGuid: string;
  menuTypeGuid: string;
  supplementList: Record<string, number>;
  priceWithDiscount: number;
  quantity: number;
  name: string;
  typeName: string;
  price: number;
}

/** Сохранённый заказ (история) */
export interface SavedOrder {
  id: string;
  date: string;
  total: number;
  items: CartItem[];
}

/** Нормализованная позиция: всегда typeList */
export function getTypeList(item: MenuItem): MenuType[] {
  const list = item.typeList ?? item.recipeTypeList;
  if (list?.length) return list;
  if (item.price != null) {
    return [{ guid: item.guid, name: '', price: item.price }];
  }
  return [];
}
