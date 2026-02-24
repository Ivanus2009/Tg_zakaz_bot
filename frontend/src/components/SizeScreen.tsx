import type { MenuItem, MenuType } from "../types";

interface SizeScreenProps {
  item: MenuItem;
  typeList: MenuType[];
  selectedType: MenuType | null;
  quantity: number;
  onSelectType: (t: MenuType) => void;
  onQuantityChange: (delta: number) => void;
  onNext: () => void;
}

export function SizeScreen({
  item,
  typeList,
  selectedType,
  quantity,
  onSelectType,
  onQuantityChange,
  onNext,
}: SizeScreenProps) {
  return (
    <div className="screen active">
      <div className="size-screen">
        <div className="item-header">
          <div className="item-header-name">{item.name}</div>
        </div>
        <div className="size-options">
          {typeList.map((type) => (
            <button
              key={type.guid}
              type="button"
              className={`size-option ${selectedType?.guid === type.guid ? "selected" : ""}`}
              onClick={() => onSelectType(type)}
            >
              <div className="size-option-name">{type.name}</div>
              <div className="size-option-price">{type.price} ₽</div>
            </button>
          ))}
        </div>
        <div className="quantity-section">
          <div className="quantity-label">Количество</div>
          <div className="quantity-controls">
            <button
              type="button"
              className="quantity-btn"
              onClick={() => onQuantityChange(-1)}
            >
              −
            </button>
            <span className="quantity-value">{quantity}</span>
            <button
              type="button"
              className="quantity-btn"
              onClick={() => onQuantityChange(1)}
            >
              +
            </button>
          </div>
        </div>
        <button type="button" className="btn-primary" onClick={onNext}>
          Далее
        </button>
      </div>
    </div>
  );
}
