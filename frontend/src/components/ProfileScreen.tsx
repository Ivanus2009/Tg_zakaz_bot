import type { SavedOrder } from "../types";
import type { AuthUser } from "../api";

interface ProfileScreenProps {
  userName: string;
  orders: SavedOrder[];
  siteUser?: AuthUser | null;
  onLinkCard?: () => void;
}

export function ProfileScreen({ userName, orders, siteUser, onLinkCard }: ProfileScreenProps) {
  return (
    <div className="screen active">
      <div className="profile-screen">
        <div className="profile-header">
          <div className="profile-avatar">👤</div>
          <div className="profile-name">{userName}</div>
        </div>
        {siteUser && (
          <div className="profile-card-section">
            {siteUser.saved_payment_method_id ? (
              <div className="profile-card-badge">💳 Карта привязана</div>
            ) : onLinkCard ? (
              <button type="button" className="btn-primary profile-link-card-btn" onClick={onLinkCard}>
                💳 Привязать карту
              </button>
            ) : null}
          </div>
        )}
        <div className="orders-list">
          {orders.length === 0 && (
            <div className="empty-state">История заказов пуста</div>
          )}
          {orders.map((order) => (
            <div key={order.id} className="order-item">
              <div className="order-header">
                <div>
                  <div className="order-id">Заказ #{order.id}</div>
                  <div className="order-date">{order.date}</div>
                </div>
                <div className="order-total">{order.total.toFixed(2)} ₽</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
