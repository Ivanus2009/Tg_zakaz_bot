import type { CartItem } from '../types';

export type PaymentMethod = 'cash' | 'online';

interface CartModalProps {
  isOpen: boolean;
  items: CartItem[];
  total: number;
  comment: string;
  paymentMethod: PaymentMethod;
  onPaymentMethodChange: (method: PaymentMethod) => void;
  onCommentChange: (value: string) => void;
  onClose: () => void;
  onCheckout: () => void;
  onRemoveItem: (index: number) => void;
}

export function CartModal({
  isOpen,
  items,
  total,
  comment,
  paymentMethod,
  onPaymentMethodChange,
  onCommentChange,
  onClose,
  onCheckout,
  onRemoveItem,
}: CartModalProps) {
  if (!isOpen) return null;

  return (
    <div
      className={`cart-modal ${isOpen ? 'active' : ''}`}
      onClick={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-label="Корзина"
    >
      <div className="cart-panel" onClick={(e) => e.stopPropagation()}>
        <div className="cart-header">
          <div className="cart-title">Корзина</div>
          <button type="button" className="cart-close" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="cart-content">
          {items.length === 0 && (
            <div className="empty-state">Корзина пуста</div>
          )}
          {items.map((item, index) => {
            const itemTotal = item.price * item.quantity;
            return (
              <div key={`${item.menuItemGuid}-${item.menuTypeGuid}-${index}`} className="cart-item">
                <div className="cart-item-info">
                  <div className="cart-item-name">{item.name}</div>
                  <div className="cart-item-details">
                    {item.typeName} × {item.quantity}
                  </div>
                </div>
                <div className="cart-item-right">
                  <span className="cart-item-price">{itemTotal.toFixed(2)} ₽</span>
                  <button
                    type="button"
                    className="cart-item-remove"
                    onClick={() => onRemoveItem(index)}
                    title="Удалить"
                    aria-label="Удалить позицию"
                  >
                    ✕
                  </button>
                </div>
              </div>
            );
          })}
          {items.length > 0 && (
            <>
              <div className="cart-payment-method">
                <span className="cart-payment-label">Способ оплаты</span>
                <div className="cart-payment-options">
                  <label className="cart-payment-option">
                    <input
                      type="radio"
                      name="payment"
                      checked={paymentMethod === 'cash'}
                      onChange={() => onPaymentMethodChange('cash')}
                    />
                    <span>💵 Оплата при получении</span>
                  </label>
                  <label className="cart-payment-option">
                    <input
                      type="radio"
                      name="payment"
                      checked={paymentMethod === 'online'}
                      onChange={() => onPaymentMethodChange('online')}
                    />
                    <span>💳 Оплатить онлайн</span>
                  </label>
                </div>
              </div>
              <div className="cart-comment">
                <label htmlFor="order-comment">Комментарий к заказу</label>
                <input
                  id="order-comment"
                  type="text"
                  className="cart-comment-input"
                  placeholder="Пожелания, адрес (если нужно)"
                  value={comment}
                  onChange={(e) => onCommentChange(e.target.value)}
                />
              </div>
            </>
          )}
        </div>
        <div className="cart-footer">
          <div className="cart-total">
            <span className="cart-total-label">Итого:</span>
            <span className="cart-total-value">{total.toFixed(2)} ₽</span>
          </div>
          <button type="button" className="btn-primary" onClick={onCheckout}>
            Оформить заказ
          </button>
        </div>
      </div>
    </div>
  );
}
