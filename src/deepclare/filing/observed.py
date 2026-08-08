"""The filing contract as the accepted declarations actually express it.

**Generated from evidence, not written by hand.** Derived from the ground-truth
declarations in the evaluation corpus by reading every element and every parent's
child order. Regenerate it rather than editing it, and regenerate it again whenever a
further accepted filing arrives.

This exists because the field specification names leaf elements freely and is silent on
most container names and on nearly every child sequence. Guessing either is fatal in a
way that gives no diagnostic: wrong child order is rejected as "wrong format" naming no
field. These names and orders are attested, so they are not guesses.

Evidence base: 71 accepted-shaped declarations.
"""

from __future__ import annotations

CASE_COUNT = 71

NAMESPACE_PREFIX: dict[str, str] = {
    'Address': 'cat_ru',
    'CUESADDeliveryTerms': 'catESAD_cu',
    'ContainerIndicator': 'catESAD_cu',
    'ContractCurrencyCode': 'catESAD_cu',
    'CounryName': 'cat_ru',
    'CountryCode': 'cat_ru',
    'CustomsCostCorrectMethod': 'catESAD_cu',
    'CustomsCountryCode': 'ESADout_CU',
    'CustomsDuty': 'catESAD_cu',
    'CustomsModeCode': 'ESADout_CU',
    'CustomsOffice': 'ESADout_CU',
    'CustomsProcedure': 'ESADout_CU',
    'CustomsTax': 'catESAD_cu',
    'DeliveryTermsStringCode': 'cat_ru',
    'DestinationCountryCode': 'catESAD_cu',
    'DestinationCountryName': 'catESAD_cu',
    'ESADCustomsProcedure': 'ESADout_CU',
    'ESADGoodsPackaging': 'ESADout_CU',
    'ESADout_CU': 'ESADout_CU',
    'ESADout_CUBorderTransport': 'ESADout_CU',
    'ESADout_CUConsigment': 'ESADout_CU',
    'ESADout_CUConsignee': 'ESADout_CU',
    'ESADout_CUConsignor': 'ESADout_CU',
    'ESADout_CUDeclarant': 'ESADout_CU',
    'ESADout_CUDepartureArrivalTransport': 'ESADout_CU',
    'ESADout_CUFinancialAdjustingResponsiblePerson': 'ESADout_CU',
    'ESADout_CUGoods': 'ESADout_CU',
    'ESADout_CUGoodsLocation': 'ESADout_CU',
    'ESADout_CUGoodsShipment': 'ESADout_CU',
    'ESADout_CUMainContractTerms': 'ESADout_CU',
    'FilledPerson': 'ESADout_CU',
    'GoodsDescription': 'catESAD_cu',
    'GoodsNumeric': 'catESAD_cu',
    'GoodsQuantity': 'cat_ru',
    'GoodsTNVEDCode': 'catESAD_cu',
    'GoodsTransferFeature': 'catESAD_cu',
    'GrossWeightQuantity': 'catESAD_cu',
    'InformationTypeCode': 'ESADout_CU',
    'InvoicedCost': 'catESAD_cu',
    'MainCustomsModeCode': 'catESAD_cu',
    'MeasureUnitQualifierCode': 'cat_ru',
    'MeasureUnitQualifierName': 'cat_ru',
    'NetWeightQuantity': 'catESAD_cu',
    'OrganizationName': 'cat_ru',
    'OriginCountryCode': 'catESAD_cu',
    'OriginCountryName': 'catESAD_cu',
    'PackingCode': 'catESAD_cu',
    'PackingInformation': 'catESAD_cu',
    'PakageQuantity': 'catESAD_cu',
    'PakageTypeCode': 'catESAD_cu',
    'PakingQuantity': 'catESAD_cu',
    'PersonName': 'cat_ru',
    'PersonSurname': 'cat_ru',
    'PrecedingCustomsModeCode': 'catESAD_cu',
    'Preferencii': 'catESAD_cu',
    'RAOrganizationFeatures': 'cat_ru',
    'Rate': 'catESAD_cu',
    'SpecificationListNumber': 'catESAD_cu',
    'SpecificationNumber': 'catESAD_cu',
    'StreetHouse': 'cat_ru',
    'SupplementaryGoodsQuantity': 'ESADout_CU',
    'TotalGoodsNumber': 'catESAD_cu',
    'TotalInvoiceAmount': 'catESAD_cu',
    'TotalPackageNumber': 'catESAD_cu',
    'TotalSheetNumber': 'catESAD_cu',
    'TradeCountryCode': 'catESAD_cu',
    'TransportModeCode': 'cat_ru',
    'UNN': 'cat_ru',
}
"""Local element name to its namespace prefix. Every name appears under exactly one
prefix across the whole evidence base, so this mapping is unambiguous."""

CHILD_ORDER: dict[str, tuple[str, ...]] = {
    'Address': (
        'CountryCode',
        'CounryName',
        'StreetHouse',
    ),
    'CUESADDeliveryTerms': (
        'DeliveryTermsStringCode',
    ),
    'ESADCustomsProcedure': (
        'MainCustomsModeCode',
        'PrecedingCustomsModeCode',
        'GoodsTransferFeature',
    ),
    'ESADGoodsPackaging': (
        'PakageQuantity',
        'PakageTypeCode',
        'PackingInformation',
    ),
    'ESADout_CU': (
        'CustomsProcedure',
        'CustomsModeCode',
        'ESADout_CUGoodsShipment',
        'FilledPerson',
    ),
    'ESADout_CUBorderTransport': (
        'TransportModeCode',
    ),
    'ESADout_CUConsigment': (
        'ContainerIndicator',
        'DestinationCountryCode',
        'DestinationCountryName',
        'ESADout_CUDepartureArrivalTransport',
        'ESADout_CUBorderTransport',
    ),
    'ESADout_CUConsignee': (
        'OrganizationName',
        'RAOrganizationFeatures',
        'Address',
    ),
    'ESADout_CUConsignor': (
        'OrganizationName',
        'Address',
    ),
    'ESADout_CUDeclarant': (
        'OrganizationName',
        'RAOrganizationFeatures',
        'Address',
    ),
    'ESADout_CUDepartureArrivalTransport': (
        'TransportModeCode',
    ),
    'ESADout_CUFinancialAdjustingResponsiblePerson': (
        'OrganizationName',
        'RAOrganizationFeatures',
        'Address',
    ),
    'ESADout_CUGoods': (
        'GoodsNumeric',
        'GoodsDescription',
        'GrossWeightQuantity',
        'NetWeightQuantity',
        'InvoicedCost',
        'GoodsTNVEDCode',
        'OriginCountryCode',
        'OriginCountryName',
        'CustomsCostCorrectMethod',
        'Preferencii',
        'SupplementaryGoodsQuantity',
        'ESADGoodsPackaging',
        'ESADCustomsProcedure',
    ),
    'ESADout_CUGoodsLocation': (
        'InformationTypeCode',
        'CustomsOffice',
        'CustomsCountryCode',
    ),
    'ESADout_CUGoodsShipment': (
        'OriginCountryName',
        'SpecificationNumber',
        'SpecificationListNumber',
        'TotalGoodsNumber',
        'TotalPackageNumber',
        'TotalSheetNumber',
        'ESADout_CUConsignor',
        'ESADout_CUConsignee',
        'ESADout_CUFinancialAdjustingResponsiblePerson',
        'ESADout_CUDeclarant',
        'ESADout_CUGoodsLocation',
        'ESADout_CUConsigment',
        'ESADout_CUMainContractTerms',
        'ESADout_CUGoods',
    ),
    'ESADout_CUMainContractTerms': (
        'ContractCurrencyCode',
        'TotalInvoiceAmount',
        'TradeCountryCode',
        'CUESADDeliveryTerms',
    ),
    'FilledPerson': (
        'PersonSurname',
        'PersonName',
    ),
    'PackingInformation': (
        'PackingCode',
        'PakingQuantity',
    ),
    'Preferencii': (
        'CustomsTax',
        'CustomsDuty',
        'Rate',
    ),
    'RAOrganizationFeatures': (
        'UNN',
    ),
    'SupplementaryGoodsQuantity': (
        'GoodsQuantity',
        'MeasureUnitQualifierName',
        'MeasureUnitQualifierCode',
    ),
}
"""Container to its children in contract order. Optional children are simply absent in
some filings; the order of those present is what must hold."""

REPEATABLE: frozenset[str] = frozenset({
    'ESADout_CUGoods',
})
"""Elements that legitimately appear more than once under one parent."""
