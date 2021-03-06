

from app.friend_collection.batch_per_thread import split_into_batches

def test_split_into_batches():
    batches = split_into_batches([0,1,2,3,4,5,6,7,8,9,10], 3)
    assert list(batches) == [
        [0, 1, 2],
        [3, 4, 5],
        [6, 7, 8],
        [9, 10]
    ]
