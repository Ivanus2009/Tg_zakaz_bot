"""Клиент YTimes API для работы с торговыми точками."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

import httpx
from dotenv import load_dotenv


API_BASE_URL = "https://api.ytimes.ru/ex"
ENV_VAR_API_KEY = "YT_API_KEY"
ENV_VAR_SHOP_GUID = "YT_SHOP_GUID"

load_dotenv()


class YTimesAPIError(Exception):
    """Базовое исключение для ошибок при обращении к YTimes API."""

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class Shop:
    """Модель торговой точки."""

    guid: str
    name: str
    type: str
    city_name: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Shop":
        return cls(
            guid=data["guid"],
            name=data["name"],
            type=data["type"],
            city_name=data.get("cityName"),
        )


class YTimesAPIClient:
    """Клиент для обращения к внешнему API YTimes."""

    def __init__(self, api_key: str, *, timeout: float = 10.0, shop_guid: Optional[str] = None) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._shop_guid = shop_guid

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """Базовый метод выполнения HTTP-запроса к API."""

        url = f"{API_BASE_URL}{path}"
        headers = {
            "Authorization": self._api_key,
            "Accept": "application/json;charset=UTF-8",
            "Content-Type": "application/json;charset=UTF-8",
        }

        try:
            response = httpx.request(
                method,
                url,
                headers=headers,
                timeout=self._timeout,
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise YTimesAPIError(f"Ошибка сети при запросе {url}: {exc}") from exc

        if response.status_code != httpx.codes.OK:
            raise YTimesAPIError(
                f"Ошибка ответа API {response.status_code}: {response.text}",
                status_code=response.status_code,
            )

        payload = response.json()
        if not payload.get("success", False):
            raise YTimesAPIError(payload.get("error") or "Неизвестная ошибка API")

        return payload

    @classmethod
    def from_env(
        cls,
        *,
        timeout: float = 10.0,
        env_var: str = ENV_VAR_API_KEY,
        shop_guid_var: str = ENV_VAR_SHOP_GUID,
    ) -> "YTimesAPIClient":
        """Создать клиента, считав ключ API из .env / переменных окружения."""

        api_key = os.getenv(env_var)
        if not api_key:
            raise YTimesAPIError(
                f"Не найден ключ API в переменной окружения {env_var}. "
                "Создайте файл .env (пример в example.env) и задайте YT_API_KEY."
            )
        shop_guid = os.getenv(shop_guid_var) or None
        return cls(api_key=api_key, timeout=timeout, shop_guid=shop_guid)

    def _resolve_shop_guid(self, shop_guid: Optional[str]) -> str:
        resolved = shop_guid or self._shop_guid
        if not resolved:
            raise YTimesAPIError(
                "Не задан GUID торговой точки. Добавьте переменную YT_SHOP_GUID в .env "
                "или передайте shop_guid при инициализации клиента/вызове метода."
            )
        return resolved

    @property
    def default_shop_guid(self) -> str:
        """GUID торговой точки, заданный через .env."""

        if not self._shop_guid:
            raise YTimesAPIError(
                "Не задан GUID торговой точки. Добавьте переменную YT_SHOP_GUID в .env "
                "или передайте shop_guid при инициализации клиента."
            )
        return self._shop_guid

    def list_shops(self) -> List[Shop]:
        """Получить список торговых точек аккаунта."""

        payload = self._request("GET", "/shop/list")
        rows = payload.get("rows") or []
        return [Shop.from_dict(row) for row in rows]

    def get_shop_guid_by_name(self, shop_name: str) -> Optional[str]:
        """Найти guid торговой точки по её названию."""

        shops = self.list_shops()
        for shop in shops:
            if shop.name == shop_name:
                return shop.guid
        return None

    def get_menu_groups(self, shop_guid: Optional[str] = None) -> List[dict]:
        """Получить структуру групп меню (v2)."""

        guid = self._resolve_shop_guid(shop_guid)
        payload = self._request(
            "GET",
            "/menu/v2/group/list",
            params={"shopGuid": guid},
        )
        return payload.get("rows") or []

    def get_menu_items(self, shop_guid: Optional[str] = None) -> List[dict]:
        """Получить структуру меню (блюда и товары) для торговой точки."""

        guid = self._resolve_shop_guid(shop_guid)
        payload = self._request(
            "GET",
            "/menu/item/list",
            params={"shopGuid": guid},
        )
        return payload.get("rows") or []

    def get_supplements(self, shop_guid: Optional[str] = None) -> List[dict]:
        """Получить список добавок/модификаторов для торговой точки."""

        guid = self._resolve_shop_guid(shop_guid)
        payload = self._request(
            "GET",
            "/menu/supplement/list",
            params={"shopGuid": guid},
        )
        return payload.get("rows") or []

    @staticmethod
    def _normalize_client_for_order(client: dict) -> dict:
        """Привести client к формату YTimes: name, cardNumber, phoneCode, phone, email."""
        name = client.get("name") or "Гость"
        email = client.get("email") or ""
        raw_phone = (client.get("phone") or "").strip()
        digits = "".join(c for c in raw_phone if c.isdigit())
        if digits.startswith("8") and len(digits) >= 11:
            phone = digits[1:]
        elif digits.startswith("7") and len(digits) >= 11:
            phone = digits[1:]
        else:
            phone = digits if digits else ""
        return {
            "name": name,
            "cardNumber": None,
            "phoneCode": "+7",
            "phone": phone[:15],
            "email": email,
        }

    def create_order(
        self,
        order_guid: str,
        shop_guid: str,
        order_type: str,
        items: list[dict],
        client: Optional[dict] = None,
        comment: Optional[str] = None,
        paid_value: Optional[float] = None,
        print_fiscal_check: bool = False,
        print_fiscal_check_email: Optional[str] = None,
    ) -> dict:
        """
        Создать заказ в YTimes.

        Args:
            order_guid: UUID заказа (ключ идемпотентности)
            shop_guid: GUID торговой точки
            order_type: TOGO, IN, DELIVERY, PRE_ORDER
            items: Список позиций (menuItemGuid, menuTypeGuid?, supplementList, priceWithDiscount, quantity)
            client: Данные клиента (name, phone?, email?) — приводятся к формату YTimes
            comment: Комментарий к заказу
            paid_value: Оплаченная сумма; None = оплата при получении
            print_fiscal_check: Печатать ли фискальный чек
            print_fiscal_check_email: Email для чека

        Returns:
            Созданный заказ (rows[0]) с guid и status
        """
        order_data = {
            "guid": order_guid,
            "shopGuid": shop_guid,
            "type": order_type,
            "itemList": items,
            "comment": comment or "",
            "paidValue": paid_value,
            "printFiscalCheck": print_fiscal_check,
            "printFiscalCheckEmail": print_fiscal_check_email,
        }

        if client:
            order_data["client"] = self._normalize_client_for_order(client)

        payload = self._request("POST", "/order/save", json=order_data)
        rows = payload.get("rows") or []
        if not rows:
            raise YTimesAPIError("Ответ API order/save не содержит заказа")
        return rows[0]

