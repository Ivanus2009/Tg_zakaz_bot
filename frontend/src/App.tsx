import { useState, useEffect, useCallback } from 'react';
import { NavBar } from './components/NavBar';
import { MenuScreen } from './components/MenuScreen';
import { SizeScreen } from './components/SizeScreen';
import { SupplementsScreen } from './components/SupplementsScreen';
import { ProfileScreen } from './components/ProfileScreen';
import { CartModal, type PaymentMethod } from './components/CartModal';
import { AuthModal } from './components/AuthModal';
import { useTelegram } from './hooks/useTelegram';
import { fetchMenu, fetchSupplements, createOrder, createInAppPayment, getMe, setStoredToken } from './api';
import type { AuthUser } from './api';
import type {
  MenuItem,
  MenuType,
  MenuGroup,
  SupplementCategory,
  CartItem,
  SavedOrder,
} from './types';
import { getTypeList } from './types';

const ORDERS_STORAGE_KEY = 'orders';

function loadOrdersFromStorage(): SavedOrder[] {
  try {
    const raw = localStorage.getItem(ORDERS_STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    // ignore
  }
  return [];
}

function saveOrdersToStorage(orders: SavedOrder[]) {
  try {
    localStorage.setItem(ORDERS_STORAGE_KEY, JSON.stringify(orders));
  } catch {
    // ignore
  }
}

type ScreenId = 'menu' | 'size' | 'supplements' | 'profile';

export default function App() {
  const { user, showAlert, showConfirm, sendData, openLink, getTelegramUser, canSendToBot } = useTelegram();

  const [menuGroup, setMenuGroup] = useState<MenuGroup | null>(null);
  const [menuLoading, setMenuLoading] = useState(true);
  const [menuError, setMenuError] = useState<string | null>(null);
  const [supplementsData, setSupplementsData] = useState<SupplementCategory[]>([]);

  const [cart, setCart] = useState<CartItem[]>([]);
  const [screen, setScreen] = useState<ScreenId>('menu');
  const [screenHistory, setScreenHistory] = useState<ScreenId[]>([]);
  const [cartOpen, setCartOpen] = useState(false);
  const [orders, setOrders] = useState<SavedOrder[]>(loadOrdersFromStorage);

  const [currentItem, setCurrentItem] = useState<MenuItem | null>(null);
  const [selectedType, setSelectedType] = useState<MenuType | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [selectedSupplements, setSelectedSupplements] = useState<Record<string, boolean>>({});
  const [orderComment, setOrderComment] = useState('');
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('cash');
  const [clientName, setClientName] = useState('');
  const [clientPhone, setClientPhone] = useState('');
  const [siteUser, setSiteUser] = useState<AuthUser | null>(null);
  const [authModalOpen, setAuthModalOpen] = useState(false);

  const menuItems = menuGroup?.itemList ?? [];

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setMenuLoading(true);
      setMenuError(null);
      try {
        const group = await fetchMenu();
        if (!cancelled) setMenuGroup(group);
        const supps = await fetchSupplements();
        if (!cancelled) setSupplementsData(supps);
      } catch (e) {
        if (!cancelled) setMenuError(e instanceof Error ? e.message : 'Ошибка загрузки');
      } finally {
        if (!cancelled) setMenuLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    (async () => {
      const res = await getMe();
      if (res.success && res.user) setSiteUser(res.user);
    })();
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const success = params.get('payment_success');
    const orderId = params.get('order_id');
    const failed = params.get('payment_failed');
    if (success === '1' && orderId) {
      window.history.replaceState({}, '', window.location.pathname || '/');
      showAlert(`✅ Заказ #${orderId} успешно оплачен! Спасибо за заказ.`);
    } else if (failed === '1') {
      window.history.replaceState({}, '', window.location.pathname || '/');
      showAlert('Оплата не прошла или была отменена. Попробуйте снова или выберите «Оплата при получении».');
    } else if (params.get('card_linked') === '1') {
      window.history.replaceState({}, '', window.location.pathname || '/');
      showAlert('Карта успешно привязана к аккаунту.');
    }
  }, [showAlert]);

  useEffect(() => {
    const tgUser = getTelegramUser?.();
    if (tgUser) {
      setClientName((n) => n || tgUser.first_name || '');
      setClientPhone((p) => p || (tgUser as { phone?: string }).phone || '');
    }
  }, [getTelegramUser]);

  useEffect(() => {
    if (siteUser) {
      setClientName((n) => n || siteUser.name || '');
      setClientPhone((p) => p || siteUser.phone || '');
    }
  }, [siteUser]);

  const goTo = useCallback((next: ScreenId, addToHistory = true) => {
    if (addToHistory && screen !== next) {
      setScreenHistory((h) => [...h, screen]);
    }
    setScreen(next);
  }, [screen]);

  const goBack = useCallback(() => {
    if (screenHistory.length === 0) {
      setScreen('menu');
      return;
    }
    const prev = screenHistory[screenHistory.length - 1];
    setScreenHistory((h) => h.slice(0, -1));
    setScreen(prev);
  }, [screenHistory]);

  const addToCartSimple = useCallback(
    (item: MenuItem) => {
      const typeList = getTypeList(item);
      const type = typeList[0];
      if (!type) return;
      const cartItem: CartItem = {
        menuItemGuid: item.guid,
        menuTypeGuid: type.guid,
        supplementList: {},
        priceWithDiscount: type.price,
        quantity: 1,
        name: item.name,
        typeName: type.name || '',
        price: type.price,
      };
      setCart((c) => [...c, cartItem]);
      showAlert('Добавлено в корзину');
    },
    [showAlert]
  );

  const selectItem = useCallback(
    (item: MenuItem) => {
      setCurrentItem(item);
      setQuantity(1);
      setSelectedSupplements({});
      const typeList = getTypeList(item);
      const hasSizes = typeList.length > 1;
      const hasSupplements =
        item.supplementCategoryToFreeCount &&
        Object.keys(item.supplementCategoryToFreeCount).length > 0;

      if (!hasSizes && !hasSupplements) {
        addToCartSimple(item);
        return;
      }
      if (!hasSizes && hasSupplements) {
        setSelectedType(typeList[0] ?? null);
        goTo('supplements');
        return;
      }
      setSelectedType(typeList[0] ?? null);
      goTo('size');
    },
    [addToCartSimple, goTo]
  );

  const goToSupplements = useCallback(() => {
    if (!selectedType) {
      showAlert('Выберите размер');
      return;
    }
    goTo('supplements');
  }, [selectedType, showAlert, goTo]);

  const addToCartFromSize = useCallback(() => {
    if (!currentItem || !selectedType) return;
    const cartItem: CartItem = {
      menuItemGuid: currentItem.guid,
      menuTypeGuid: selectedType.guid,
      supplementList: {},
      priceWithDiscount: selectedType.price,
      quantity,
      name: currentItem.name,
      typeName: selectedType.name || '',
      price: selectedType.price,
    };
    setCart((c) => [...c, cartItem]);
    setScreenHistory([]);
    setScreen('menu');
    setCurrentItem(null);
    setSelectedType(null);
    setSelectedSupplements({});
    showAlert('Добавлено в корзину');
  }, [currentItem, selectedType, quantity, showAlert]);

  const supplementCategoriesForCurrentItem = (): SupplementCategory[] => {
    if (!currentItem?.supplementCategoryToFreeCount) return [];
    const guids = Object.keys(currentItem.supplementCategoryToFreeCount);
    return supplementsData.filter((c) => guids.includes(c.guid));
  };

  const toggleSupplement = useCallback((guid: string) => {
    setSelectedSupplements((s) => ({ ...s, [guid]: !s[guid] }));
  }, []);

  const addToCartFromSupplements = useCallback(() => {
    if (!currentItem) return;
    const typeList = getTypeList(currentItem);
    const type = selectedType ?? typeList[0];
    if (!type) return;

    const categories = supplementCategoriesForCurrentItem();
    const supplements: Record<string, number> = {};
    let totalPrice = type.price;

    categories.forEach((cat) => {
      cat.itemList?.forEach((supp) => {
        if (selectedSupplements[supp.guid]) {
          supplements[supp.guid] = 1;
          totalPrice += supp.defaultPrice ?? 0;
        }
      });
    });

    const cartItem: CartItem = {
      menuItemGuid: currentItem.guid,
      menuTypeGuid: type.guid,
      supplementList: supplements,
      priceWithDiscount: totalPrice,
      quantity,
      name: currentItem.name,
      typeName: type.name || '',
      price: totalPrice,
    };
    setCart((c) => [...c, cartItem]);
    setScreenHistory([]);
    setScreen('menu');
    setCurrentItem(null);
    setSelectedType(null);
    setSelectedSupplements({});
    showAlert('Добавлено в корзину');
  }, [
    currentItem,
    selectedType,
    quantity,
    selectedSupplements,
    showAlert,
  ]);

  const cartCount = cart.reduce((sum, item) => sum + item.quantity, 0);
  const cartTotal = cart.reduce((sum, item) => sum + item.price * item.quantity, 0);

  const removeFromCart = useCallback((index: number) => {
    setCart((c) => c.filter((_, i) => i !== index));
  }, []);

  const checkout = useCallback(() => {
    if (cart.length === 0) {
      showAlert('Корзина пуста');
      return;
    }
    const name = clientName.trim();
    const phone = clientPhone.trim();
    if (!name) {
      showAlert('Укажите имя');
      return;
    }
    if (!phone) {
      showAlert('Укажите телефон');
      return;
    }
    const currentUser = getTelegramUser?.() ?? user;
    const total = cartTotal;
    const baseOrderPayload = {
      items: cart.map((item) => ({
        menuItemGuid: item.menuItemGuid,
        menuTypeGuid: item.menuTypeGuid,
        supplementList: item.supplementList,
        priceWithDiscount: item.priceWithDiscount,
        quantity: item.quantity,
      })),
      client: { name, phone, email: '' },
      comment: orderComment.trim() || undefined,
      telegramUserId: currentUser?.id,
    };

    if (paymentMethod === 'online') {
      showConfirm('Оформить заказ с оплатой картой?', (confirmed) => {
        if (!confirmed) return;
        (async () => {
          try {
            const result = await createInAppPayment(baseOrderPayload);
            if (!result.success) {
              showAlert(result.error || 'Не удалось создать платёж');
              return;
            }
            const url = result.confirmation_url;
            if (!url) {
              showAlert('Ошибка: нет ссылки на оплату');
              return;
            }
            setCart([]);
            setCartOpen(false);
            setScreenHistory([]);
            setScreen('menu');
            showAlert('Откроется страница оплаты. После оплаты вы вернётесь в приложение.');
            openLink(url);
          } catch (e) {
            showAlert('Ошибка: ' + (e instanceof Error ? e.message : 'Сеть'));
          }
        })();
      });
      return;
    }

    showConfirm('Оформить заказ?', (confirmed) => {
      if (!confirmed) return;
      (async () => {
        try {
          const orderData = {
            type: 'TOGO',
            ...baseOrderPayload,
            paidValue: 0,
          };
          const result = await createOrder(orderData);
          if (result.success && result.order_id != null) {
            const savedOrder: SavedOrder = {
              id: result.order_id,
              date: new Date().toLocaleString('ru-RU'),
              total,
              items: [...cart],
            };
            setOrders((o) => {
              const next = [savedOrder, ...o];
              saveOrdersToStorage(next);
              return next;
            });
            if (canSendToBot) {
              sendData({
                action: 'order_created',
                order_id: result.order_id,
                total,
                paid: false,
              });
            }
            setCart([]);
            setCartOpen(false);
            setScreenHistory([]);
            setScreen('menu');
            showAlert(
              `✅ Заказ #${result.order_id} успешно сформирован!\n💰 Сумма: ${total.toFixed(2)} ₽`
            );
          } else {
            showAlert('Ошибка: ' + (result.error || 'Неизвестная ошибка'));
          }
        } catch (e) {
          showAlert('Ошибка: ' + (e instanceof Error ? e.message : 'Сеть'));
        }
      })();
    });
  }, [
    cart,
    cartTotal,
    user,
    clientName,
    clientPhone,
    orderComment,
    paymentMethod,
    showAlert,
    showConfirm,
    sendData,
    openLink,
    getTelegramUser,
    canSendToBot,
  ]);

  const showProfile = useCallback(() => goTo('profile'), [goTo]);
  const handleLogout = useCallback(() => {
    setStoredToken(null);
    setSiteUser(null);
  }, []);

  return (
    <>
      <NavBar
        screen={screen}
        cartCount={cartCount}
        onBack={goBack}
        onProfile={showProfile}
        onCart={() => setCartOpen(true)}
        siteUser={siteUser}
        onLoginClick={() => setAuthModalOpen(true)}
        onLogout={handleLogout}
      />

      {screen === 'menu' && (
        <MenuScreen
          items={menuItems}
          loading={menuLoading}
          error={menuError}
          onSelectItem={selectItem}
        />
      )}

      {screen === 'size' && currentItem && (
        <SizeScreen
          item={currentItem}
          typeList={getTypeList(currentItem)}
          selectedType={selectedType}
          quantity={quantity}
          onSelectType={setSelectedType}
          onQuantityChange={(delta) => setQuantity((q) => Math.max(1, q + delta))}
          onNext={goToSupplements}
          onAddWithoutSupplements={addToCartFromSize}
          hasSupplementsScreen={supplementCategoriesForCurrentItem().length > 0}
        />
      )}

      {screen === 'supplements' && currentItem && (
        <SupplementsScreen
          itemName={currentItem.name}
          categories={supplementCategoriesForCurrentItem()}
          selectedSupplements={selectedSupplements}
          onToggleSupplement={toggleSupplement}
          onAddToCart={addToCartFromSupplements}
        />
      )}

      {screen === 'profile' && (
        <ProfileScreen
          userName={siteUser?.name || siteUser?.phone || user?.first_name || 'Пользователь'}
          orders={orders}
          siteUser={siteUser}
          onLinkCard={
            siteUser
              ? async () => {
                  const { linkCard } = await import('./api');
                  const r = await linkCard();
                  if (r.success && r.confirmation_url) openLink(r.confirmation_url);
                  else showAlert(r.error || 'Ошибка привязки карты');
                }
              : undefined
          }
        />
      )}

      <CartModal
        isOpen={cartOpen}
        items={cart}
        total={cartTotal}
        clientName={clientName}
        clientPhone={clientPhone}
        onClientNameChange={setClientName}
        onClientPhoneChange={setClientPhone}
        comment={orderComment}
        paymentMethod={paymentMethod}
        onPaymentMethodChange={setPaymentMethod}
        onCommentChange={setOrderComment}
        onClose={() => setCartOpen(false)}
        onCheckout={checkout}
        onRemoveItem={removeFromCart}
      />
      <AuthModal
        isOpen={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
        onSuccess={() => getMe().then((r) => r.success && r.user && setSiteUser(r.user))}
      />
    </>
  );
}
