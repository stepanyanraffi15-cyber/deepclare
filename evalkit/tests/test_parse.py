import unittest

from evalkit.parse import parse_declaration

_XML = """
<ESADout_CU><ESADout_CUGoodsShipment>
  <TotalGoodsNumber>2</TotalGoodsNumber>
  <TotalPackageNumber>15</TotalPackageNumber>
  <TotalCustCost>1500.5</TotalCustCost>
  <CustCostCurrencyCode>USD</CustCostCurrencyCode>
  <ESADout_CUGoods>
    <GoodsNumeric>1</GoodsNumeric>
    <GoodsDescription>ՌԵԼԵ ABB</GoodsDescription>
    <GoodsTNVEDCode>8536100000</GoodsTNVEDCode>
    <OriginCountryCode>DE</OriginCountryCode>
    <NetWeightQuantity>100</NetWeightQuantity>
    <GrossWeightQuantity>110</GrossWeightQuantity>
    <InvoicedCost>500</InvoicedCost>
    <GoodsQuantity>100</GoodsQuantity>
    <MeasureUnitQualifierCode>166</MeasureUnitQualifierCode>
    <ESADGoodsPackaging><PakageQuantity>5</PakageQuantity></ESADGoodsPackaging>
  </ESADout_CUGoods>
  <ESADout_CUGoods>
    <GoodsNumeric>2</GoodsNumeric>
    <GoodsDescription>ՊՈՂՊԱՏԵ ՊՏՈՒՏԱԿ</GoodsDescription>
    <GoodsTNVEDCode>7318 15 000 0</GoodsTNVEDCode>
    <OriginCountryCode>CN</OriginCountryCode>
    <NetWeightQuantity>200</NetWeightQuantity>
    <GrossWeightQuantity>210</GrossWeightQuantity>
    <InvoicedCost>1000,5</InvoicedCost>
    <GoodsQuantity>200</GoodsQuantity>
    <MeasureUnitQualifierCode>166</MeasureUnitQualifierCode>
    <ESADGoodsPackaging><PakageQuantity>10</PakageQuantity></ESADGoodsPackaging>
  </ESADout_CUGoods>
</ESADout_CUGoodsShipment></ESADout_CU>
"""


class ParseTests(unittest.TestCase):
    def test_shipment_totals(self) -> None:
        d = parse_declaration(_XML)
        self.assertEqual(d.total_goods, 2)
        self.assertEqual(d.total_packages, 15.0)
        self.assertEqual(d.total_cost, 1500.5)
        self.assertEqual(d.currency, "USD")

    def test_goods_fields(self) -> None:
        d = parse_declaration(_XML)
        self.assertEqual(len(d.goods), 2)
        g1 = d.goods[0]
        self.assertEqual(g1.numeric, 1)
        self.assertEqual(g1.description, "ՌԵԼԵ ABB")
        self.assertEqual(g1.hs_code, "8536100000")
        self.assertEqual(g1.origin, "DE")
        self.assertEqual(g1.unit, "166")
        self.assertEqual(g1.net_weight, 100.0)
        self.assertEqual(g1.package_count, 5.0)

    def test_number_normalisation(self) -> None:
        d = parse_declaration(_XML)
        # comma decimal parsed; whitespace-formatted code preserved verbatim in text
        self.assertEqual(d.goods[1].invoiced_cost, 1000.5)
        self.assertEqual(d.goods[1].hs_code, "7318 15 000 0")


if __name__ == "__main__":
    unittest.main()
