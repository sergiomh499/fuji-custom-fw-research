"""Fujifilm X-T5 model definition."""

from .base import CameraModel


class XT5Model(CameraModel):
    """Fujifilm X-T5 camera model (X-Processor 5 / 40.2MP X-Trans V HR)."""

    def __init__(self):
        super().__init__(
            id="xt5",
            name="Fujifilm X-T5",
            model_code_prefix="0005688",
            processor="X-Processor 5",
            sensor="40.2MP X-Trans CMOS V HR (APS-C)",
            latest_fw="4.31",
            fw_filename="FWUP0030.DAT",
            dl_url="https://dl.fujifilm-x.com/support/firmware/x-t5-431-a7wr26ib/FWUP0030.DAT",
            virtual_delta=0x0135FFB8,
            known_offsets={
                "FSIM_NOSTALGIC_NEG": 0x00000000,
                "FSIM_BLEACH_BYPASS": 0x00000000,
                "FSIM_REALA_ACE": 0x00000000,
            },
        )


XT5_MODEL = XT5Model()
