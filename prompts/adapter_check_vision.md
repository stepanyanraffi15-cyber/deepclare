---
name: adapter_check_vision
version: 1
---

You are checking that an image reaches the model and that the answer comes back in the
requested shape. Nothing here is domain work.

The image is a {{width}} by {{height}} rectangle split down the middle into two solid
colours.

## Output contract

Name the colour of the left half and the colour of the right half, each as a single
lowercase English colour word, and state how many distinct colours you can see.
